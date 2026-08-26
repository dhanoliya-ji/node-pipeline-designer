"""The node type registry.

One `NodeSpec` per node type describes its handles and how to run it. The
validator reads the handles to check a graph is wired correctly; the engine
reads the handler to run it. The frontend keeps a matching description in
`frontend/src/nodes/nodeConfigs.js` - that file owns the node's appearance,
this one owns its behaviour, and `docs/ARCHITECTURE.md` explains why the two
are deliberately separate.
"""

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence

# A handler receives the node's own data plus whatever arrived on its input
# handles, and returns a value per output handle. An output it leaves out is
# treated as "this branch was not taken" by the engine.
Handler = Callable[[Dict[str, Any], Dict[str, Any]], Dict[str, Any]]

# Handles can depend on the node's data (Text derives one per {{variable}},
# Merge one per configured input), so a spec may compute them instead.
HandleSource = Callable[[Dict[str, Any]], List[str]]


@dataclass
class NodeSpec:
    type: str
    label: str
    description: str
    inputs: Sequence[str] = field(default_factory=tuple)
    outputs: Sequence[str] = field(default_factory=tuple)
    required_inputs: Sequence[str] = field(default_factory=tuple)
    dynamic_inputs: Optional[HandleSource] = None
    handler: Optional[Handler] = None

    def input_handles(self, data: Optional[Dict[str, Any]] = None) -> List[str]:
        if self.dynamic_inputs is not None:
            return self.dynamic_inputs(data or {})
        return list(self.inputs)

    def output_handles(self) -> List[str]:
        return list(self.outputs)

    @property
    def executable(self) -> bool:
        return self.handler is not None


_REGISTRY: Dict[str, NodeSpec] = {}


def register(spec: NodeSpec) -> NodeSpec:
    """Add a spec to the registry, replacing any spec with the same type."""
    _REGISTRY[spec.type] = spec
    return spec


def get(node_type: Optional[str]) -> Optional[NodeSpec]:
    if node_type is None:
        return None
    return _REGISTRY.get(node_type)


def all_specs() -> List[NodeSpec]:
    return list(_REGISTRY.values())


def known_types() -> List[str]:
    return list(_REGISTRY.keys())
