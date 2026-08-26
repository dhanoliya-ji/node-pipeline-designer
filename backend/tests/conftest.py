"""Shared fixtures and builders.

The helpers here keep the tests readable: a test says what shape of graph it
is about, not how to assemble Pydantic models.
"""

import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import pytest

# Tests run from the repository root as well as from backend/, so the package
# root is put on the path explicitly rather than relying on the cwd.
BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.schemas import Edge, Node  # noqa: E402


def node(node_id: str, node_type: Optional[str] = None, **data: Any) -> Node:
    return Node(id=node_id, type=node_type, data=dict(data) if data else {})


def edge(
    source: str,
    target: str,
    source_handle: Optional[str] = None,
    target_handle: Optional[str] = None,
    edge_id: Optional[str] = None,
) -> Edge:
    """Build an edge, prefixing handles the way the canvas does.

    React Flow emits handle ids as `${nodeId}-${handleName}`, so the tests
    exercise that real format instead of a convenient bare name.
    """
    return Edge(
        id=edge_id or '{}->{}'.format(source, target),
        source=source,
        target=target,
        sourceHandle='{}-{}'.format(source, source_handle) if source_handle else None,
        targetHandle='{}-{}'.format(target, target_handle) if target_handle else None,
    )


def chain(length: int) -> Tuple[List[Node], List[Edge]]:
    """A straight line of `length` untyped nodes: n0 -> n1 -> ... -> n(length-1)."""
    nodes = [node('n{}'.format(i)) for i in range(length)]
    edges = [edge('n{}'.format(i), 'n{}'.format(i + 1)) for i in range(length - 1)]
    return nodes, edges


def ring(length: int) -> Tuple[List[Node], List[Edge]]:
    """A chain whose last node points back at the first, so it is cyclic."""
    nodes, edges = chain(length)
    edges.append(edge('n{}'.format(length - 1), 'n0'))
    return nodes, edges


@pytest.fixture
def linear_pipeline() -> Tuple[List[Node], List[Edge]]:
    """Input -> Text -> Output, fully wired and runnable.

    The Text node's template uses {{name}}, so it grows one input handle
    called `name`, which is what the Input node connects to.
    """
    nodes = [
        node('customInput-1', 'customInput', inputName='name',
             inputType='Text', inputValue='Ada'),
        node('text-1', 'text', text='Hello, {{name}}!'),
        node('customOutput-1', 'customOutput', outputName='greeting',
             outputType='Text'),
    ]
    edges = [
        edge('customInput-1', 'text-1', 'value', 'name'),
        edge('text-1', 'customOutput-1', 'output', 'value'),
    ]
    return nodes, edges


@pytest.fixture
def branching_pipeline() -> Tuple[List[Node], List[Edge]]:
    """Input -> Condition, with an Output on each branch.

    Only one of the two Outputs should ever receive a value, which is what
    makes this the fixture for the engine's skip behaviour.
    """
    nodes = [
        node('customInput-1', 'customInput', inputName='score',
             inputType='Number', inputValue='75'),
        node('condition-1', 'condition', expression='value > 50'),
        node('customOutput-1', 'customOutput', outputName='high'),
        node('customOutput-2', 'customOutput', outputName='low'),
    ]
    edges = [
        edge('customInput-1', 'condition-1', 'value', 'value'),
        edge('condition-1', 'customOutput-1', 'true', 'value'),
        edge('condition-1', 'customOutput-2', 'false', 'value'),
    ]
    return nodes, edges
