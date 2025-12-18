# ==============================================================================
# dot_parser.py - CDFG DOT File Parser
# ==============================================================================
"""Parser for CDFG (Control Data Flow Graph) DOT Files from gem5-SALAM.

This module parses Graphviz DOT format files exported by gem5-SALAM's
LLVMInterface::exportCDFGToDot() function. These files describe the
dataflow graph of accelerator computations.

DOT File Structure::

    digraph CDFG {
        // Subgraphs for functions
        subgraph cluster_func_0 {
            label="Function: compute_kernel"

            // Subgraphs for basic blocks
            subgraph cluster_bb_0 {
                label="BB: entry"

                // Nodes represent instructions
                n0 [label="load\\nUID:0\\nCycles:3" fillcolor=lightblue]
                n1 [label="fmul\\nUID:1\\nCycles:5" fillcolor=lightgreen]
                n2 [label="store\\nUID:2\\nCycles:3" fillcolor=lightblue]
            }
        }

        // Edges represent dependencies
        n0 -> n1 [color=blue]              // Data dependency
        n0 -> n2 [style=dashed, color=red] // Control flow
        n1 -> n2 [style=dotted, color=gray] // Sequence (same BB)
    }

Data Classes:
    - InstructionNode: Represents a single instruction
    - CDFGEdge: Represents a dependency edge
    - CDFGGraph: Container for the complete graph

Edge Types:
    | Type     | Style   | Color | Meaning                    |
    |----------|---------|-------|----------------------------|
    | data     | Solid   | Blue  | Data dependency (RAW)      |
    | control  | Dashed  | Red   | Control flow               |
    | sequence | Dotted  | Gray  | Ordering within basic block|

Node Colors (set by gem5-SALAM):
    | Color        | Instruction Type        |
    |--------------|-------------------------|
    | lightblue    | Memory operations       |
    | lightgreen   | Compute operations      |
    | lightyellow  | Control flow            |
    | lightpink    | Phi nodes (SSA)         |
    | lightsalmon  | Call/invoke             |
    | white        | Default/unknown         |

Example:
    Parsing and analyzing a CDFG::

        from salam_gui.data.dot_parser import (
            parse_cdfg_dot, get_node_positions
        )
        from pathlib import Path

        # Parse DOT file
        graph = parse_cdfg_dot(Path("m5out/cdfg.dot"))

        # Access nodes
        for uid, node in graph.nodes.items():
            print(f"{node.opcode} (UID:{uid}) - {node.cycles} cycles")

        # Access edges
        for edge in graph.edges:
            print(f"{edge.source} -> {edge.target} ({edge.edge_type})")

        # Convert to NetworkX for analysis
        nx_graph = graph.nx_graph
        print(f"Nodes: {nx_graph.number_of_nodes()}")
        print(f"Edges: {nx_graph.number_of_edges()}")

        # Get layout positions for visualization
        positions = get_node_positions(graph)

Layout Algorithms:
    - Uses Graphviz 'dot' layout if available (best for DAGs)
    - Falls back to NetworkX spring_layout

See Also:
    - cdfg_viewer: Visualizes parsed CDFG
    - LLVMInterface::exportCDFGToDot(): C++ export function
"""


__version__ = "3.0.0.pre[1.0.0]"

import re
from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
import networkx as nx


@dataclass
class InstructionNode:
    """Represents a single instruction in the CDFG."""
    uid: int
    opcode: str
    cycles: int
    color: str = "white"
    basic_block: Optional[str] = None
    function: Optional[str] = None

    @property
    def label(self) -> str:
        return f"{self.opcode}\nUID:{self.uid}\nCycles:{self.cycles}"


@dataclass
class CDFGEdge:
    """Represents an edge in the CDFG."""
    source: int
    target: int
    edge_type: str  # 'data', 'control', 'sequence'
    label: str = ""


@dataclass
class CDFGGraph:
    """Container for parsed CDFG data."""
    nodes: Dict[int, InstructionNode] = field(default_factory=dict)
    edges: List[CDFGEdge] = field(default_factory=list)
    functions: Dict[str, List[str]] = field(default_factory=dict)  # func -> [bbs]
    basic_blocks: Dict[str, List[int]] = field(default_factory=dict)  # bb -> [uids]

    @property
    def nx_graph(self) -> nx.DiGraph:
        """Convert to NetworkX graph for layout algorithms."""
        G = nx.DiGraph()

        for uid, node in self.nodes.items():
            G.add_node(
                uid,
                label=node.label,
                opcode=node.opcode,
                cycles=node.cycles,
                color=node.color,
                bb=node.basic_block,
                func=node.function
            )

        for edge in self.edges:
            G.add_edge(
                edge.source,
                edge.target,
                edge_type=edge.edge_type,
                label=edge.label
            )

        return G


def parse_cdfg_dot(file_path: Path) -> CDFGGraph:
    """
    Parse a CDFG DOT file into a CDFGGraph structure.

    Args:
        file_path: Path to the .dot file

    Returns:
        CDFGGraph containing parsed nodes and edges
    """
    content = file_path.read_text()
    graph = CDFGGraph()

    # Track current context
    current_function = None
    current_bb = None

    # Regex patterns
    func_pattern = re.compile(
        r'subgraph\s+cluster_func_(\d+)\s*\{[^}]*label="Function:\s*([^"]+)"',
        re.DOTALL
    )
    bb_pattern = re.compile(
        r'subgraph\s+cluster_bb_(\d+)\s*\{[^}]*label="BB:\s*([^"]+)"',
        re.DOTALL
    )
    node_pattern = re.compile(
        r'n(\d+)\s*\[label="(\w+)\\nUID:(\d+)\\nCycles:(\d+)"'
        r'[^]]*fillcolor=(\w+)',
        re.MULTILINE
    )
    # Edge patterns
    data_edge_pattern = re.compile(
        r'n(\d+)\s*->\s*n(\d+)\s*\[color=blue',
        re.MULTILINE
    )
    control_edge_pattern = re.compile(
        r'n(\d+)\s*->\s*n(\d+)\s*\[style=dashed,\s*color=red',
        re.MULTILINE
    )
    seq_edge_pattern = re.compile(
        r'n(\d+)\s*->\s*n(\d+)\s*\[style=dotted,\s*color=gray',
        re.MULTILINE
    )

    # Parse functions
    for match in func_pattern.finditer(content):
        func_id = match.group(1)
        func_name = match.group(2)
        graph.functions[func_name] = []

    # Parse basic blocks
    for match in bb_pattern.finditer(content):
        bb_id = match.group(1)
        bb_name = match.group(2)
        graph.basic_blocks[bb_name] = []

    # Parse nodes
    for match in node_pattern.finditer(content):
        uid = int(match.group(3))
        node = InstructionNode(
            uid=uid,
            opcode=match.group(2),
            cycles=int(match.group(4)),
            color=match.group(5)
        )
        graph.nodes[uid] = node

    # Parse data dependency edges
    for match in data_edge_pattern.finditer(content):
        edge = CDFGEdge(
            source=int(match.group(1)),
            target=int(match.group(2)),
            edge_type='data'
        )
        graph.edges.append(edge)

    # Parse control flow edges
    for match in control_edge_pattern.finditer(content):
        edge = CDFGEdge(
            source=int(match.group(1)),
            target=int(match.group(2)),
            edge_type='control',
            label='cf'
        )
        graph.edges.append(edge)

    # Parse sequence edges (within basic block)
    for match in seq_edge_pattern.finditer(content):
        edge = CDFGEdge(
            source=int(match.group(1)),
            target=int(match.group(2)),
            edge_type='sequence'
        )
        graph.edges.append(edge)

    return graph


def get_node_positions(graph: CDFGGraph) -> Dict[int, Tuple[float, float]]:
    """
    Calculate node positions using NetworkX layout algorithms.

    Args:
        graph: The CDFG graph

    Returns:
        Dictionary mapping node UIDs to (x, y) positions
    """
    G = graph.nx_graph

    if len(G.nodes) == 0:
        return {}

    # Try hierarchical layout first (good for dataflow)
    try:
        # Use dot layout if graphviz is available
        from networkx.drawing.nx_agraph import graphviz_layout
        pos = graphviz_layout(G, prog='dot')
    except (ImportError, Exception):
        # Fall back to spring layout
        pos = nx.spring_layout(G, k=2, iterations=50)

    return pos
