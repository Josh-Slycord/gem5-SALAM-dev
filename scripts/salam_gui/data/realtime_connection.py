# ==============================================================================
# realtime_connection.py - Live Simulation Connection via ZeroMQ
# ==============================================================================
"""Real-Time Connection to Running gem5-SALAM Simulations.

This module provides ZeroMQ-based communication with running gem5-SALAM
simulations for live monitoring and real-time visualization updates.
Enables the GUI to display simulation progress as it happens.

Architecture::

    gem5-SALAM Simulation                    SALAM GUI
    +--------------------+                 +-------------------+
    | LLVMInterface      |                 | SimulationReceiver|
    |   - ZMQ PUB socket |  == ZeroMQ ==>  |   - ZMQ SUB socket|
    |   - JSON messages  |   tcp://5555    |   - QThread       |
    +--------------------+                 +-------------------+
                                                    |
                                                    v
                                           +-------------------+
                                           |SimulationConnection|
                                           |  - Signal dispatch|
                                           |  - Handler registry|
                                           +-------------------+
                                                    |
                                                    v
                                           +-------------------+
                                           | LiveDataBuffer    |
                                           |   - Thread-safe   |
                                           |   - History limit |
                                           +-------------------+

Message Types:
    | Type                 | Description                    | Data Fields        |
    |----------------------|--------------------------------|--------------------|
    | cycle_update         | Current simulation cycle       | cycle              |
    | queue_state          | Queue depths                   | read, write, comp  |
    | fu_state             | FU utilization                 | per-FU utilization |
    | instruction_issue    | Instruction dispatched         | uid, opcode        |
    | instruction_complete | Instruction finished           | uid, cycles        |
    | stall_event          | Stall occurred                 | uid, type, reason  |
    | stats_update         | Periodic statistics            | various metrics    |
    | sim_start            | Simulation beginning           | benchmark, config  |
    | sim_end              | Simulation complete            | total_cycles       |
    | heartbeat            | Keep-alive                     | timestamp          |

Connection States:
    - DISCONNECTED: No active connection
    - CONNECTING: Attempting to connect
    - CONNECTED: Active connection receiving data
    - ERROR: Connection failed

Classes:
    - ConnectionState: Enum of connection states
    - MessageType: Enum of message types
    - SimulationMessage: Parsed message dataclass
    - SimulationReceiver: QThread for ZMQ reception
    - SimulationConnection: High-level connection manager
    - LiveDataBuffer: Thread-safe data accumulator

Example:
    Connecting to a live simulation::

        from salam_gui.data.realtime_connection import (
            SimulationConnection, MessageType
        )

        # Create connection manager
        conn = SimulationConnection()

        # Connect signals to update UI
        conn.cycle_updated.connect(lambda c: print(f"Cycle: {c}"))
        conn.queue_state_updated.connect(update_queue_display)
        conn.simulation_ended.connect(on_sim_complete)

        # Connect to simulation
        conn.connect("tcp://localhost:5555")

        # ... simulation runs ...

        # Disconnect when done
        conn.disconnect()

Requirements:
    - PyZMQ: pip install pyzmq
    - gem5-SALAM must be built with ZMQ support
    - Simulation must enable ZMQ publisher

Default Address:
    tcp://localhost:5555

See Also:
    - connection_dialog: UI for configuring connection
    - queue_monitor: Consumes real-time queue data
    - fu_utilization: Consumes real-time FU data
"""


__version__ = "3.0.0.pre[1.0.0]"

import json
import threading
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Callable, Dict, Any, List
from queue import Queue

import zmq

from PySide6.QtCore import QObject, Signal, QThread


class ConnectionState(Enum):
    """Connection states."""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"


class MessageType(Enum):
    """Types of messages from the simulation."""
    CYCLE_UPDATE = "cycle_update"
    QUEUE_STATE = "queue_state"
    FU_STATE = "fu_state"
    INSTRUCTION_ISSUE = "instruction_issue"
    INSTRUCTION_COMPLETE = "instruction_complete"
    STALL_EVENT = "stall_event"
    STATS_UPDATE = "stats_update"
    SIMULATION_START = "sim_start"
    SIMULATION_END = "sim_end"
    HEARTBEAT = "heartbeat"


@dataclass
class SimulationMessage:
    """A message received from the simulation."""
    msg_type: MessageType
    cycle: int
    data: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = 0.0


class SimulationReceiver(QThread):
    """
    Background thread that receives messages from a running simulation.

    Uses ZeroMQ SUB socket to receive published simulation events.
    """

    # Signals emitted when data is received
    message_received = Signal(object)  # SimulationMessage
    connection_changed = Signal(str)   # ConnectionState name
    error_occurred = Signal(str)       # Error message

    def __init__(self, parent=None):
        super().__init__(parent)
        self.address = ""
        self.running = False
        self.context: Optional[zmq.Context] = None
        self.socket: Optional[zmq.Socket] = None
        self._stop_flag = threading.Event()

    def connect_to(self, address: str):
        """Set the address to connect to."""
        self.address = address

    def run(self):
        """Main receiver loop - runs in background thread."""
        self.running = True
        self._stop_flag.clear()

        try:
            self.context = zmq.Context()
            self.socket = self.context.socket(zmq.SUB)

            # Subscribe to all messages
            self.socket.setsockopt_string(zmq.SUBSCRIBE, "")

            # Set receive timeout for clean shutdown
            self.socket.setsockopt(zmq.RCVTIMEO, 1000)  # 1 second timeout

            self.connection_changed.emit(ConnectionState.CONNECTING.name)
            self.socket.connect(self.address)
            self.connection_changed.emit(ConnectionState.CONNECTED.name)

            while not self._stop_flag.is_set():
                try:
                    # Receive message (with timeout)
                    raw_msg = self.socket.recv_string(flags=0)

                    # Parse JSON message
                    msg_data = json.loads(raw_msg)

                    # Convert to SimulationMessage
                    msg = self._parse_message(msg_data)
                    if msg:
                        self.message_received.emit(msg)

                except zmq.Again:
                    # Timeout - check if we should stop
                    continue
                except json.JSONDecodeError as e:
                    self.error_occurred.emit(f"Invalid JSON: {e}")
                except Exception as e:
                    self.error_occurred.emit(f"Receive error: {e}")

        except zmq.ZMQError as e:
            self.error_occurred.emit(f"ZMQ Error: {e}")
            self.connection_changed.emit(ConnectionState.ERROR.name)
        finally:
            self._cleanup()
            self.connection_changed.emit(ConnectionState.DISCONNECTED.name)
            self.running = False

    def _parse_message(self, data: Dict[str, Any]) -> Optional[SimulationMessage]:
        """Parse raw message data into SimulationMessage."""
        try:
            msg_type_str = data.get("type", "")

            # Map string to MessageType
            try:
                msg_type = MessageType(msg_type_str)
            except ValueError:
                # Unknown message type - skip
                return None

            return SimulationMessage(
                msg_type=msg_type,
                cycle=data.get("cycle", 0),
                data=data.get("data", {}),
                timestamp=data.get("timestamp", 0.0)
            )
        except Exception:
            return None

    def stop(self):
        """Signal the receiver to stop."""
        self._stop_flag.set()

    def _cleanup(self):
        """Clean up ZeroMQ resources."""
        if self.socket:
            self.socket.close()
            self.socket = None
        if self.context:
            self.context.term()
            self.context = None


class SimulationConnection(QObject):
    """
    Manages connection to a running gem5-SALAM simulation.

    Provides high-level interface for connecting/disconnecting and
    dispatches received messages to registered handlers.
    """

    # Connection state signals
    connected = Signal()
    disconnected = Signal()
    connection_error = Signal(str)

    # Data signals (processed from raw messages)
    cycle_updated = Signal(int)
    queue_state_updated = Signal(dict)
    fu_state_updated = Signal(dict)
    instruction_issued = Signal(dict)
    instruction_completed = Signal(dict)
    stall_occurred = Signal(dict)
    stats_updated = Signal(dict)
    simulation_started = Signal(dict)
    simulation_ended = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.receiver: Optional[SimulationReceiver] = None
        self.state = ConnectionState.DISCONNECTED
        self.current_cycle = 0

        # Message handlers
        self._handlers: Dict[MessageType, List[Callable]] = {
            msg_type: [] for msg_type in MessageType
        }

    @property
    def is_connected(self) -> bool:
        return self.state == ConnectionState.CONNECTED

    def connect(self, address: str = "tcp://localhost:5555"):
        """
        Connect to a running simulation.

        Args:
            address: ZeroMQ address (e.g., "tcp://localhost:5555")
        """
        if self.receiver and self.receiver.isRunning():
            self.disconnect()

        self.receiver = SimulationReceiver(self)
        self.receiver.connect_to(address)

        # Connect signals
        self.receiver.message_received.connect(self._on_message_received)
        self.receiver.connection_changed.connect(self._on_connection_changed)
        self.receiver.error_occurred.connect(self._on_error)

        # Start receiver thread
        self.receiver.start()

    def disconnect(self):
        """Disconnect from the simulation."""
        if self.receiver:
            self.receiver.stop()
            self.receiver.wait(2000)  # Wait up to 2 seconds
            self.receiver = None
        self.state = ConnectionState.DISCONNECTED
        self.disconnected.emit()

    def register_handler(self, msg_type: MessageType, handler: Callable[[SimulationMessage], None]):
        """Register a handler for a specific message type."""
        self._handlers[msg_type].append(handler)

    def unregister_handler(self, msg_type: MessageType, handler: Callable):
        """Unregister a message handler."""
        if handler in self._handlers[msg_type]:
            self._handlers[msg_type].remove(handler)

    def _on_message_received(self, msg: SimulationMessage):
        """Handle received message - dispatch to appropriate signal/handlers."""
        # Update current cycle
        if msg.cycle > self.current_cycle:
            self.current_cycle = msg.cycle
            self.cycle_updated.emit(msg.cycle)

        # Emit type-specific signal
        if msg.msg_type == MessageType.QUEUE_STATE:
            self.queue_state_updated.emit(msg.data)
        elif msg.msg_type == MessageType.FU_STATE:
            self.fu_state_updated.emit(msg.data)
        elif msg.msg_type == MessageType.INSTRUCTION_ISSUE:
            self.instruction_issued.emit(msg.data)
        elif msg.msg_type == MessageType.INSTRUCTION_COMPLETE:
            self.instruction_completed.emit(msg.data)
        elif msg.msg_type == MessageType.STALL_EVENT:
            self.stall_occurred.emit(msg.data)
        elif msg.msg_type == MessageType.STATS_UPDATE:
            self.stats_updated.emit(msg.data)
        elif msg.msg_type == MessageType.SIMULATION_START:
            self.simulation_started.emit(msg.data)
        elif msg.msg_type == MessageType.SIMULATION_END:
            self.simulation_ended.emit(msg.data)

        # Call registered handlers
        for handler in self._handlers.get(msg.msg_type, []):
            try:
                handler(msg)
            except Exception as e:
                print(f"Handler error: {e}")

    def _on_connection_changed(self, state_name: str):
        """Handle connection state change."""
        try:
            self.state = ConnectionState[state_name]
        except KeyError:
            return

        if self.state == ConnectionState.CONNECTED:
            self.connected.emit()
        elif self.state == ConnectionState.DISCONNECTED:
            self.disconnected.emit()

    def _on_error(self, error_msg: str):
        """Handle connection error."""
        self.state = ConnectionState.ERROR
        self.connection_error.emit(error_msg)


class LiveDataBuffer:
    """
    Buffer for accumulating live data for widget updates.

    Aggregates high-frequency updates and provides periodic snapshots
    to avoid overwhelming the UI.
    """

    def __init__(self, max_history: int = 10000):
        self.max_history = max_history
        self.queue_history: List[Dict[str, Any]] = []
        self.fu_history: List[Dict[str, Any]] = []
        self.instruction_events: List[Dict[str, Any]] = []
        self.stall_events: List[Dict[str, Any]] = []
        self._lock = threading.Lock()

    def add_queue_state(self, cycle: int, state: Dict[str, Any]):
        """Add queue state snapshot."""
        with self._lock:
            self.queue_history.append({"cycle": cycle, **state})
            if len(self.queue_history) > self.max_history:
                self.queue_history = self.queue_history[-self.max_history:]

    def add_fu_state(self, cycle: int, state: Dict[str, Any]):
        """Add FU state snapshot."""
        with self._lock:
            self.fu_history.append({"cycle": cycle, **state})
            if len(self.fu_history) > self.max_history:
                self.fu_history = self.fu_history[-self.max_history:]

    def add_instruction_event(self, event: Dict[str, Any]):
        """Add instruction issue/complete event."""
        with self._lock:
            self.instruction_events.append(event)
            if len(self.instruction_events) > self.max_history:
                self.instruction_events = self.instruction_events[-self.max_history:]

    def add_stall_event(self, event: Dict[str, Any]):
        """Add stall event."""
        with self._lock:
            self.stall_events.append(event)
            if len(self.stall_events) > self.max_history:
                self.stall_events = self.stall_events[-self.max_history:]

    def get_queue_history(self) -> List[Dict[str, Any]]:
        """Get copy of queue history."""
        with self._lock:
            return list(self.queue_history)

    def get_fu_history(self) -> List[Dict[str, Any]]:
        """Get copy of FU history."""
        with self._lock:
            return list(self.fu_history)

    def clear(self):
        """Clear all buffered data."""
        with self._lock:
            self.queue_history.clear()
            self.fu_history.clear()
            self.instruction_events.clear()
            self.stall_events.clear()
