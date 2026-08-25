"""Wire format shared by the canvas and the API.

The frontend decorates nodes and edges with a lot of view state (positions,
z-index, handle geometry). None of it is modelled here: the API reads the
graph, not the drawing.
"""

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

Severity = Literal['error', 'warning', 'info']


class Node(BaseModel):
    id: str
    type: Optional[str] = None
    data: Optional[Dict[str, Any]] = None


class Edge(BaseModel):
    id: Optional[str] = None
    source: str
    target: str
    sourceHandle: Optional[str] = None
    targetHandle: Optional[str] = None


class Pipeline(BaseModel):
    nodes: List[Node] = Field(default_factory=list)
    edges: List[Edge] = Field(default_factory=list)


class Issue(BaseModel):
    """One problem found in a pipeline, addressed to a node or an edge."""

    code: str
    severity: Severity
    message: str
    node_id: Optional[str] = None
    edge_id: Optional[str] = None


class PipelineStats(BaseModel):
    """The response of /pipelines/parse.

    `num_nodes`, `num_edges` and `is_dag` are the original three fields and
    keep their names; everything below them is additive.
    """

    num_nodes: int
    num_edges: int
    is_dag: bool

    # Structure, derived from the same topological pass that answers is_dag.
    cycles: List[List[str]] = Field(default_factory=list)
    topological_order: List[str] = Field(default_factory=list)
    depth: int = 0
    entry_points: List[str] = Field(default_factory=list)
    exit_points: List[str] = Field(default_factory=list)
    isolated_nodes: List[str] = Field(default_factory=list)

    # Semantics, from the validation pass.
    issues: List[Issue] = Field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return self.is_dag and not any(i.severity == 'error' for i in self.issues)


class ValidationReport(BaseModel):
    """The response of /pipelines/validate."""

    is_dag: bool
    is_valid: bool
    issues: List[Issue] = Field(default_factory=list)
    topological_order: List[str] = Field(default_factory=list)


class ExecutionStep(BaseModel):
    """What one node did during a run."""

    node_id: str
    node_type: Optional[str] = None
    status: Literal['ok', 'skipped', 'error']
    outputs: Dict[str, Any] = Field(default_factory=dict)
    duration_ms: float = 0.0
    message: Optional[str] = None


class ExecutionReport(BaseModel):
    """The response of /pipelines/execute."""

    status: Literal['ok', 'error']
    steps: List[ExecutionStep] = Field(default_factory=list)
    outputs: Dict[str, Any] = Field(default_factory=dict)
    duration_ms: float = 0.0
    issues: List[Issue] = Field(default_factory=list)


class NodeDescriptor(BaseModel):
    """A node type the engine knows how to run, for /nodes."""

    type: str
    label: str
    description: str
    inputs: List[str] = Field(default_factory=list)
    outputs: List[str] = Field(default_factory=list)
    executable: bool = True
