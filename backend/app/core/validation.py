"""Semantic validation.

`graph.py` answers whether a pipeline is *shaped* correctly. This module
answers whether it is *wired* correctly: are the required inputs connected,
do the edges land on handles that exist, is anything stranded on the canvas.

Every finding is an `Issue` carrying a stable `code`, a severity, and the id
of the node or edge it belongs to, so the frontend can highlight the exact
element rather than showing a wall of text.
"""

from collections import defaultdict
from typing import Dict, List, Optional, Sequence

from ..nodes import get as get_spec
from ..schemas import Edge, Issue, Node
from .graph import GraphAnalysis, analyse

# How many nodes of a cycle are named in an issue's message before it is
# abbreviated. Past a handful, the sentence stops being readable anyway.
MAX_CYCLE_IN_MESSAGE = 8


def _handle_name(handle: Optional[str], node_id: str) -> Optional[str]:
    """Strip the node id the canvas prefixes onto every handle id.

    React Flow needs handle ids to be unique per node, so the frontend emits
    `${nodeId}-${name}`. The registry knows handles by their bare name.
    """
    if handle is None:
        return None
    prefix = node_id + '-'
    return handle[len(prefix):] if handle.startswith(prefix) else handle


def validate(
    nodes: Sequence[Node],
    edges: Sequence[Edge],
    analysis: Optional[GraphAnalysis] = None,
) -> List[Issue]:
    """Return every issue found, errors first, then warnings, then info."""
    analysis = analysis or analyse(nodes, edges)
    issues: List[Issue] = []
    by_id: Dict[str, Node] = {}
    duplicates: List[str] = []

    for node in nodes:
        if node.id in by_id:
            duplicates.append(node.id)
        else:
            by_id[node.id] = node

    if not nodes:
        return [Issue(
            code='EMPTY_PIPELINE',
            severity='info',
            message='The pipeline is empty. Drag a node onto the canvas to begin.',
        )]

    for node_id in duplicates:
        issues.append(Issue(
            code='DUPLICATE_NODE_ID',
            severity='error',
            node_id=node_id,
            message="More than one node shares the id '{}'.".format(node_id),
        ))

    # ---- Structure -------------------------------------------------------
    for cycle in analysis.cycles:
        if len(cycle) == 1:
            issues.append(Issue(
                code='SELF_LOOP',
                severity='error',
                node_id=cycle[0],
                message="'{}' is connected to itself, which is a cycle.".format(cycle[0]),
            ))
            continue
        # Built once per cycle, not once per member: a 2000-node ring would
        # otherwise spend O(V^2) assembling the same sentence V times. Long
        # cycles are abbreviated because the point is which nodes are on the
        # loop, and the node ids are listed on each issue anyway.
        if len(cycle) > MAX_CYCLE_IN_MESSAGE:
            shown = cycle[:MAX_CYCLE_IN_MESSAGE]
            chain = '{} -> … ({} more) -> {}'.format(
                ' -> '.join(shown), len(cycle) - MAX_CYCLE_IN_MESSAGE, cycle[0])
        else:
            chain = ' -> '.join(cycle + [cycle[0]])

        for node_id in cycle:
            issues.append(Issue(
                code='CYCLE',
                severity='error',
                node_id=node_id,
                message='This node sits on a cycle: {}.'.format(chain),
            ))

    for edge_id in analysis.dangling_edges:
        issues.append(Issue(
            code='DANGLING_EDGE',
            severity='error',
            edge_id=edge_id,
            message='This edge points at a node that is not on the canvas.',
        ))

    # ---- Handles ---------------------------------------------------------
    # Counted per (node, handle) so a second edge into a single-value input
    # can be reported as the ambiguity it is.
    fan_in: Dict[str, List[str]] = defaultdict(list)
    connected_inputs: Dict[str, set] = defaultdict(set)

    for index, edge in enumerate(edges):
        edge_label = edge.id or 'edge[{}]'.format(index)
        source = by_id.get(edge.source)
        target = by_id.get(edge.target)
        if source is None or target is None:
            continue  # Already reported as dangling.

        source_spec = get_spec(source.type)
        target_spec = get_spec(target.type)

        source_handle = _handle_name(edge.sourceHandle, edge.source)
        target_handle = _handle_name(edge.targetHandle, edge.target)

        if source_spec and source_handle:
            if source_handle not in source_spec.output_handles():
                issues.append(Issue(
                    code='UNKNOWN_SOURCE_HANDLE',
                    severity='error',
                    edge_id=edge_label,
                    node_id=edge.source,
                    message="'{}' has no output named '{}'.".format(
                        edge.source, source_handle),
                ))

        if target_spec and target_handle:
            valid_inputs = target_spec.input_handles(target.data)
            if target_handle not in valid_inputs:
                issues.append(Issue(
                    code='UNKNOWN_TARGET_HANDLE',
                    severity='error',
                    edge_id=edge_label,
                    node_id=edge.target,
                    message="'{}' has no input named '{}'.".format(
                        edge.target, target_handle),
                ))
            else:
                connected_inputs[edge.target].add(target_handle)
                fan_in['{}::{}'.format(edge.target, target_handle)].append(edge_label)

    for key, edge_ids in fan_in.items():
        if len(edge_ids) > 1:
            node_id, handle = key.split('::', 1)
            issues.append(Issue(
                code='AMBIGUOUS_INPUT',
                severity='error',
                node_id=node_id,
                message="{} edges feed the single input '{}' on '{}'; only one "
                        'value can arrive there.'.format(len(edge_ids), handle, node_id),
            ))

    # ---- Per-node semantics ---------------------------------------------
    has_output_node = False

    for node in by_id.values():
        spec = get_spec(node.type)
        if spec is None:
            issues.append(Issue(
                code='UNKNOWN_NODE_TYPE',
                severity='warning',
                node_id=node.id,
                message="The backend has no handler for node type '{}', so it "
                        'cannot be executed.'.format(node.type),
            ))
            continue

        if node.type == 'customOutput':
            has_output_node = True

        for required in spec.required_inputs:
            if required not in connected_inputs[node.id]:
                issues.append(Issue(
                    code='MISSING_REQUIRED_INPUT',
                    severity='error',
                    node_id=node.id,
                    message="'{}' needs its '{}' input connected.".format(
                        node.id, required),
                ))

        # Text nodes are the one place a user creates handles by typing, so a
        # variable with nothing attached is worth calling out explicitly.
        if node.type == 'text':
            for variable in spec.input_handles(node.data):
                if variable not in connected_inputs[node.id]:
                    issues.append(Issue(
                        code='UNCONNECTED_VARIABLE',
                        severity='warning',
                        node_id=node.id,
                        message="The variable '{{{{{}}}}}' has nothing connected, so "
                                'it will be left as-is in the output.'.format(variable),
                    ))

        if node.type == 'api' and not str((node.data or {}).get('url', '')).strip():
            issues.append(Issue(
                code='MISSING_URL',
                severity='error',
                node_id=node.id,
                message="'{}' has no URL configured.".format(node.id),
            ))

    # ---- Whole-pipeline hygiene -----------------------------------------
    for node_id in analysis.isolated_nodes:
        issues.append(Issue(
            code='ISOLATED_NODE',
            severity='warning',
            node_id=node_id,
            message="'{}' is not connected to anything, so it will not run.".format(node_id),
        ))

    if not has_output_node and len(nodes) > 1:
        issues.append(Issue(
            code='NO_OUTPUT_NODE',
            severity='warning',
            message='The pipeline has no Output node, so a run will produce no result.',
        ))

    order = {'error': 0, 'warning': 1, 'info': 2}
    issues.sort(key=lambda issue: order[issue.severity])
    return issues


def has_errors(issues: Sequence[Issue]) -> bool:
    return any(issue.severity == 'error' for issue in issues)
