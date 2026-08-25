"""Graph analysis.

One pass over the edge list answers every structural question the app asks:
is it a DAG, in what order do the nodes run, which nodes start it, which
nodes end it, and - when it is not a DAG - exactly which nodes form the
cycles.

Complexity is O(V + E) in time and space throughout. See
`docs/ARCHITECTURE.md` for the reasoning and `notebooks/analysis.ipynb` for
the measurements that back it up.
"""

from collections import deque
from dataclasses import dataclass, field
from typing import Dict, Iterator, List, Sequence, Set, Tuple

from ..schemas import Edge, Node


@dataclass
class GraphAnalysis:
    """Everything the structural pass learned about one pipeline."""

    node_ids: List[str] = field(default_factory=list)
    adjacency: Dict[str, List[str]] = field(default_factory=dict)
    reverse_adjacency: Dict[str, List[str]] = field(default_factory=dict)
    in_degree: Dict[str, int] = field(default_factory=dict)
    out_degree: Dict[str, int] = field(default_factory=dict)
    topological_order: List[str] = field(default_factory=list)
    cycles: List[List[str]] = field(default_factory=list)
    levels: Dict[str, int] = field(default_factory=dict)
    dangling_edges: List[str] = field(default_factory=list)

    @property
    def is_dag(self) -> bool:
        """Acyclic exactly when the topological sort covered every node."""
        return len(self.topological_order) == len(self.node_ids)

    @property
    def entry_points(self) -> List[str]:
        """Nodes nothing feeds - where a run begins."""
        return [n for n in self.node_ids if self.in_degree[n] == 0]

    @property
    def exit_points(self) -> List[str]:
        """Nodes that feed nothing - where a run ends."""
        return [n for n in self.node_ids if self.out_degree[n] == 0]

    @property
    def isolated_nodes(self) -> List[str]:
        """Nodes with no edge at all: on the canvas, but not in the pipeline."""
        return [
            n for n in self.node_ids
            if self.in_degree[n] == 0 and self.out_degree[n] == 0
        ]

    @property
    def depth(self) -> int:
        """Longest path in nodes - the number of sequential stages a run has.

        Zero for an empty graph, and reported as zero for a cyclic one, where
        no finite longest path exists.
        """
        return max(self.levels.values()) + 1 if self.levels else 0

    @property
    def cyclic_nodes(self) -> Set[str]:
        return {node_id for cycle in self.cycles for node_id in cycle}


def _build(nodes: Sequence[Node], edges: Sequence[Edge]):
    """Turn the wire format into adjacency lists.

    Duplicate node ids collapse to one entry, and an edge whose endpoint is
    not on the canvas is dropped and reported rather than silently creating a
    phantom node. A self-loop is kept: it is a real cycle, and keeping it is
    what makes Kahn's algorithm report it as one.
    """
    node_ids: List[str] = []
    seen: Set[str] = set()
    for node in nodes:
        if node.id not in seen:
            seen.add(node.id)
            node_ids.append(node.id)

    adjacency: Dict[str, List[str]] = {n: [] for n in node_ids}
    reverse: Dict[str, List[str]] = {n: [] for n in node_ids}
    in_degree: Dict[str, int] = {n: 0 for n in node_ids}
    out_degree: Dict[str, int] = {n: 0 for n in node_ids}
    dangling: List[str] = []

    for index, edge in enumerate(edges):
        if edge.source not in seen or edge.target not in seen:
            dangling.append(edge.id or 'edge[{}]'.format(index))
            continue
        adjacency[edge.source].append(edge.target)
        reverse[edge.target].append(edge.source)
        in_degree[edge.target] += 1
        out_degree[edge.source] += 1

    return node_ids, adjacency, reverse, in_degree, out_degree, dangling


def _kahn(
    node_ids: Sequence[str],
    adjacency: Dict[str, List[str]],
    in_degree: Dict[str, int],
) -> Tuple[List[str], Dict[str, int]]:
    """Kahn's algorithm, also recording each node's level.

    A node's level is one past the deepest level among its predecessors, so
    the levels double as the render layers the auto-layout uses on the canvas.
    `in_degree` is copied because callers still need the original counts.
    """
    remaining = dict(in_degree)
    queue = deque(n for n in node_ids if remaining[n] == 0)
    order: List[str] = []
    levels: Dict[str, int] = {n: 0 for n in queue}

    while queue:
        node_id = queue.popleft()
        order.append(node_id)
        for neighbour in adjacency[node_id]:
            levels[neighbour] = max(levels.get(neighbour, 0), levels[node_id] + 1)
            remaining[neighbour] -= 1
            if remaining[neighbour] == 0:
                queue.append(neighbour)

    return order, levels


def _find_cycles(
    node_ids: Sequence[str],
    adjacency: Dict[str, List[str]],
    unresolved: Set[str],
) -> List[List[str]]:
    """Name the cycles among the nodes Kahn's algorithm could not place.

    An iterative colour-marking DFS restricted to `unresolved`: when the walk
    meets a node still on the current path, the slice of the path from that
    node onward is a cycle. Iterative rather than recursive so a long chain
    cannot exhaust the interpreter's stack.
    """
    WHITE, GREY, BLACK = 0, 1, 2
    colour = {n: WHITE for n in unresolved}
    cycles: List[List[str]] = []
    fingerprints: Set[frozenset] = set()

    for root in node_ids:
        if colour.get(root, BLACK) != WHITE:
            continue

        path: List[str] = [root]
        on_path: Set[str] = {root}
        colour[root] = GREY
        # Each frame is a node plus an iterator over the neighbours left to try.
        stack: List[Tuple[str, Iterator[str]]] = [(root, iter(adjacency[root]))]

        while stack:
            node_id, neighbours = stack[-1]
            advanced = False

            for neighbour in neighbours:
                if neighbour not in colour:
                    continue  # Outside the cyclic region; Kahn already placed it.
                if neighbour in on_path:
                    cycle = path[path.index(neighbour):]
                    fingerprint = frozenset(cycle)
                    if fingerprint not in fingerprints:
                        fingerprints.add(fingerprint)
                        cycles.append(cycle)
                elif colour[neighbour] == WHITE:
                    colour[neighbour] = GREY
                    path.append(neighbour)
                    on_path.add(neighbour)
                    stack.append((neighbour, iter(adjacency[neighbour])))
                    advanced = True
                    break

            if not advanced:
                colour[node_id] = BLACK
                on_path.discard(node_id)
                if path and path[-1] == node_id:
                    path.pop()
                stack.pop()

    return cycles


def analyse(nodes: Sequence[Node], edges: Sequence[Edge]) -> GraphAnalysis:
    """Run the full structural pass over a pipeline."""
    node_ids, adjacency, reverse, in_degree, out_degree, dangling = _build(nodes, edges)
    order, levels = _kahn(node_ids, adjacency, in_degree)

    unresolved = set(node_ids) - set(order)
    cycles = _find_cycles(node_ids, adjacency, unresolved) if unresolved else []

    return GraphAnalysis(
        node_ids=node_ids,
        adjacency=adjacency,
        reverse_adjacency=reverse,
        in_degree=in_degree,
        out_degree=out_degree,
        topological_order=order,
        cycles=cycles,
        # A cyclic graph has no finite longest path, so the levels are dropped
        # rather than reported as the partial ones Kahn managed to assign.
        levels={} if unresolved else levels,
        dangling_edges=dangling,
    )


def is_dag(nodes: Sequence[Node], edges: Sequence[Edge]) -> bool:
    """Convenience wrapper for callers that only want the yes/no."""
    return analyse(nodes, edges).is_dag
