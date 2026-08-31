"""The execution engine.

Runs a pipeline by walking its topological order once and handing each node
the values that arrived on its input handles. Because the order is
topological, every predecessor of a node has already run by the time the
node does, so a single pass is enough - no scheduling, no re-entry, no
fixed-point iteration.

Branching falls out of the same rule. A handler returns a value per output
handle and may leave one out; an omitted handle means nothing flowed down
that path, so a node whose every incoming edge came up empty is *skipped*
rather than run with missing data, and the skip propagates to its subtree.
"""

import time
from typing import Any, Dict, List, Optional, Sequence, Tuple

from ..config import MAX_EDGES, MAX_NODES
from ..nodes import NodeExecutionError, get as get_spec
from ..schemas import Edge, ExecutionReport, ExecutionStep, Issue, Node
from .graph import analyse
from .validation import has_errors, validate


class PipelineTooLarge(ValueError):
    """The pipeline exceeds the configured size limits."""


def _handle_name(handle: Optional[str], node_id: str, default: Optional[str]) -> Optional[str]:
    """Bare handle name, with the canvas's `${nodeId}-` prefix removed.

    An edge drawn between nodes that each have a single handle can arrive
    without a handle id at all, so the caller supplies the sole candidate as
    the default.
    """
    if handle is None:
        return default
    prefix = node_id + '-'
    return handle[len(prefix):] if handle.startswith(prefix) else handle


def _sole_output_handle(node_id: str, produced: Dict[str, Dict[str, Any]]) -> Optional[str]:
    """The one output handle a node produced, used when an edge omits one.

    Ambiguous by design when a node produced several: an edge leaving a
    multi-output node must say which handle it left, and returning None makes
    that edge deliver nothing rather than guess.
    """
    outputs = produced.get(node_id) or {}
    real = [key for key in outputs if not key.startswith('_')]
    return real[0] if len(real) == 1 else None


def _collect_inputs(
    incoming: Sequence[Tuple[Edge, str]],
    produced: Dict[str, Dict[str, Any]],
    skipped: set,
) -> Tuple[Dict[str, Any], bool]:
    """Gather one node's inputs.

    Returns the inputs plus whether the node should run at all: a node with
    incoming edges none of which delivered a value is downstream of a branch
    that was not taken.
    """
    inputs: Dict[str, Any] = {}
    delivered = False

    for edge, target_handle in incoming:
        if edge.source in skipped:
            continue
        source_outputs = produced.get(edge.source)
        if not source_outputs:
            continue

        default = _sole_output_handle(edge.source, produced)
        source_handle = _handle_name(edge.sourceHandle, edge.source, default)
        if source_handle is None or source_handle not in source_outputs:
            continue  # The branch this edge leaves was not taken.

        inputs[target_handle] = source_outputs[source_handle]
        delivered = True

    return inputs, delivered


def execute(
    nodes: Sequence[Node],
    edges: Sequence[Edge],
    strict: bool = True,
) -> ExecutionReport:
    """Run a pipeline and report what every node did.

    With `strict` (the default) a pipeline carrying validation errors is
    refused before anything runs, which is what the API does. Passing
    `strict=False` runs whatever is runnable, which is useful in tests and
    for a partially-wired canvas.
    """
    started = time.perf_counter()

    if len(nodes) > MAX_NODES or len(edges) > MAX_EDGES:
        raise PipelineTooLarge(
            'pipeline exceeds the limit of {} nodes and {} edges'.format(
                MAX_NODES, MAX_EDGES)
        )

    analysis = analyse(nodes, edges)
    issues = validate(nodes, edges, analysis)

    if not analysis.is_dag:
        return ExecutionReport(
            status='error',
            issues=issues,
            duration_ms=(time.perf_counter() - started) * 1000,
        )

    if strict and has_errors(issues):
        return ExecutionReport(
            status='error',
            issues=issues,
            duration_ms=(time.perf_counter() - started) * 1000,
        )

    by_id = {node.id: node for node in nodes}

    # Pre-group the incoming edges so the run itself is O(V + E) rather than
    # rescanning the edge list once per node.
    incoming: Dict[str, List[Tuple[Edge, str]]] = {node.id: [] for node in nodes}
    for edge in edges:
        target = by_id.get(edge.target)
        if target is None or edge.source not in by_id:
            continue
        spec = get_spec(target.type)
        candidates = spec.input_handles(target.data) if spec else []
        default = candidates[0] if len(candidates) == 1 else None
        handle = _handle_name(edge.targetHandle, edge.target, default)
        if handle is not None:
            incoming[edge.target].append((edge, handle))

    produced: Dict[str, Dict[str, Any]] = {}
    skipped: set = set()
    steps: List[ExecutionStep] = []
    outputs: Dict[str, Any] = {}
    failed = False

    for node_id in analysis.topological_order:
        node = by_id[node_id]
        spec = get_spec(node.type)
        data = node.data or {}
        node_started = time.perf_counter()

        if spec is None or not spec.executable:
            skipped.add(node_id)
            steps.append(ExecutionStep(
                node_id=node_id,
                node_type=node.type,
                status='skipped',
                message="no handler is registered for node type '{}'".format(node.type),
            ))
            continue

        node_inputs, delivered = _collect_inputs(
            incoming[node_id], produced, skipped)

        # A node with no incoming edges is a source and always runs; one with
        # edges that all came up empty is downstream of an untaken branch.
        if incoming[node_id] and not delivered:
            skipped.add(node_id)
            steps.append(ExecutionStep(
                node_id=node_id,
                node_type=node.type,
                status='skipped',
                message='no value reached this node; an upstream branch was not taken',
                duration_ms=(time.perf_counter() - node_started) * 1000,
            ))
            continue

        try:
            result = spec.handler(data, node_inputs) or {}
        except NodeExecutionError as error:
            failed = True
            skipped.add(node_id)
            steps.append(ExecutionStep(
                node_id=node_id,
                node_type=node.type,
                status='error',
                message=str(error),
                duration_ms=(time.perf_counter() - node_started) * 1000,
            ))
            continue
        except Exception as error:  # A handler bug must not take the API down.
            failed = True
            skipped.add(node_id)
            steps.append(ExecutionStep(
                node_id=node_id,
                node_type=node.type,
                status='error',
                message='{}: {}'.format(type(error).__name__, error),
                duration_ms=(time.perf_counter() - node_started) * 1000,
            ))
            continue

        produced[node_id] = result
        # Keys starting with an underscore are handler metadata, not handles.
        visible = {k: v for k, v in result.items() if not k.startswith('_')}

        if node.type == 'customOutput':
            name = str(data.get('outputName') or node_id)
            outputs[name] = result.get('value')

        steps.append(ExecutionStep(
            node_id=node_id,
            node_type=node.type,
            status='ok',
            outputs=visible,
            duration_ms=(time.perf_counter() - node_started) * 1000,
        ))

    return ExecutionReport(
        status='error' if failed else 'ok',
        steps=steps,
        outputs=outputs,
        issues=issues,
        duration_ms=(time.perf_counter() - started) * 1000,
    )
