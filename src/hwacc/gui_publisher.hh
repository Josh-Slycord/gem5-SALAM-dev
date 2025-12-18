/**
 * @file gui_publisher.hh
 * @brief ZeroMQ publisher for real-time GUI monitoring of gem5-SALAM simulations.
 *
 * This module provides functionality to publish simulation events to an external
 * GUI application for real-time visualization and monitoring.
 */

#ifndef __HWACC_GUI_PUBLISHER_HH__
#define __HWACC_GUI_PUBLISHER_HH__

#include <string>
#include <cstdint>

// Forward declare implementation detail
namespace gem5 {
struct GUIPublisherImpl;
}

namespace gem5 {

/**
 * @brief Publisher for sending simulation events to external GUI.
 *
 * Uses ZeroMQ PUB socket to broadcast simulation events that can be
 * received by the salam_gui application for real-time visualization.
 *
 * Message format is JSON with the following structure:
 * {
 *   "type": "<message_type>",
 *   "cycle": <cycle_number>,
 *   "timestamp": <unix_timestamp>,
 *   "data": { ... type-specific data ... }
 * }
 */
class GUIPublisher {
public:
    /**
     * @brief Construct a new GUI Publisher.
     * @param address ZeroMQ bind address (default: tcp port 5555)
     * @param enabled Whether publishing is enabled
     */
    GUIPublisher(const std::string& address = "tcp://*:5555",
                 bool enabled = false);

    ~GUIPublisher();

    // Disable copy
    GUIPublisher(const GUIPublisher&) = delete;
    GUIPublisher& operator=(const GUIPublisher&) = delete;

    /**
     * @brief Initialize the ZeroMQ socket.
     * @return true if successful, false otherwise
     */
    bool initialize();

    /**
     * @brief Shutdown the publisher.
     */
    void shutdown();

    /**
     * @brief Check if publisher is enabled.
     */
    bool isEnabled() const { return enabled && initialized; }

    /**
     * @brief Enable or disable the publisher.
     */
    void setEnabled(bool enable) { enabled = enable; }

    // --- Event Publishing Methods ---

    /**
     * @brief Publish simulation start event.
     * @param simName Simulation name/identifier
     * @param accelName Accelerator name
     */
    void publishSimulationStart(const std::string& simName,
                                const std::string& accelName);

    /**
     * @brief Publish simulation end event.
     * @param totalCycles Total cycles executed
     */
    void publishSimulationEnd(uint64_t totalCycles);

    /**
     * @brief Publish cycle update (called periodically, not every cycle).
     * @param cycle Current cycle number
     */
    void publishCycleUpdate(uint64_t cycle);

    /**
     * @brief Publish queue state update.
     * @param cycle Current cycle
     * @param readQueueDepth Read queue depth
     * @param writeQueueDepth Write queue depth
     * @param computeQueueDepth Compute queue depth
     */
    void publishQueueState(uint64_t cycle,
                          int readQueueDepth,
                          int writeQueueDepth,
                          int computeQueueDepth);

    /**
     * @brief Publish functional unit state update.
     * @param cycle Current cycle
     * @param fuName FU name/type
     * @param busy Whether the FU is busy
     * @param utilization Current utilization (0.0-1.0)
     */
    void publishFUState(uint64_t cycle,
                       const std::string& fuName,
                       bool busy,
                       double utilization);

    /**
     * @brief Publish instruction issue event.
     * @param cycle Issue cycle
     * @param uid Instruction UID
     * @param opcode Instruction opcode
     * @param fuType Target FU type
     */
    void publishInstructionIssue(uint64_t cycle,
                                 int uid,
                                 const std::string& opcode,
                                 const std::string& fuType);

    /**
     * @brief Publish instruction completion event.
     * @param cycle Completion cycle
     * @param uid Instruction UID
     */
    void publishInstructionComplete(uint64_t cycle, int uid);

    /**
     * @brief Publish stall event.
     * @param cycle Stall cycle
     * @param uid Instruction UID (or -1 if N/A)
     * @param reason Stall reason
     */
    void publishStallEvent(uint64_t cycle,
                          int uid,
                          const std::string& reason);

    /**
     * @brief Publish statistics update.
     * @param cycle Current cycle
     * @param statsJson JSON string with statistics
     */
    void publishStatsUpdate(uint64_t cycle, const std::string& statsJson);

    /**
     * @brief Publish heartbeat (for connection keepalive).
     */
    void publishHeartbeat();

private:
    /**
     * @brief Send a JSON message.
     * @param jsonMsg The JSON message string
     */
    void sendMessage(const std::string& jsonMsg);

    /**
     * @brief Get current timestamp.
     */
    double getCurrentTimestamp();

    std::string address;
    bool enabled;
    bool initialized;

    // Pimpl for ZeroMQ internals (avoids incomplete type issues)
    GUIPublisherImpl* impl;

    // Rate limiting
    uint64_t lastPublishCycle;
    int publishInterval;  // Only publish every N cycles
};

/**
 * @brief Global GUI publisher instance (singleton pattern).
 *
 * Use getGUIPublisher() to access the global instance.
 */
GUIPublisher& getGUIPublisher();

/**
 * @brief Initialize the global GUI publisher.
 * @param address ZeroMQ bind address
 * @param enabled Whether to enable publishing
 */
void initGUIPublisher(const std::string& address, bool enabled);

} // namespace gem5

#endif // __HWACC_GUI_PUBLISHER_HH__
