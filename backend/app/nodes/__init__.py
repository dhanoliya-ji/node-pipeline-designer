"""Node type registry.

Importing `handlers` for its side effect is what populates the registry, so
every consumer gets a fully-loaded registry by importing this package.
"""

from . import handlers  # noqa: F401  (imported for its registration calls)
from .handlers import NodeExecutionError, extract_variables
from .registry import NodeSpec, all_specs, get, known_types, register

__all__ = [
    'NodeExecutionError',
    'NodeSpec',
    'all_specs',
    'extract_variables',
    'get',
    'known_types',
    'register',
]
