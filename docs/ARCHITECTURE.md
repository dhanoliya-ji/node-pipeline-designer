# Architecture

How the pieces fit, and why they are arranged this way.

---

## The shape of the system

```
┌─────────────────────────────── browser ───────────────────────────────┐
│                                                                       │
│  TopBar ──────── actions: validate · run · save · export · undo       │
│  NodePalette ─── drag source, generated from nodeConfigs.js           │
│  Canvas ──────── React Flow; refuses cycles as they are drawn         │
│  InspectorPanel ─ issues and run reports; clicking one selects a node │
│                                                                       │
│                    ▲                          │                       │
│            store.js (Zustand)  ◄──── nodes · edges · history          │
│                    │                          ▼                       │
│                 lib/graph.js · lib/layout.js · lib/serialize.js        │
│                    │                                                   │
└────────────────────┼───────────────────────────────────────────────────┘
                     │  POST /pipelines/{parse,validate,execute}
┌────────────────────▼───────────────────────── FastAPI ────────────────┐
│  api/routes.py ── thin adapters, no logic                             │
│       │                                                               │
│       ├── core/graph.py ──────── Kahn's algorithm, cycle DFS, metrics │
│       ├── core/validation.py ─── semantic rules → Issue[]             │
│       ├── core/engine.py ─────── single-pass topological execution    │
│       ├── core/expressions.py ── sandboxed AST evaluator              │
│       └── nodes/ ─────────────── registry + one handler per node type │
└───────────────────────────────────────────────────────────────────────┘
```

---

## The central idea: a node type is data

Most node editors pay a per-node-type cost in components, styles and
state-wiring. This one pays it once.

A node type is described by a plain object:

```javascript
{
  type: 'math',
  label: 'Math',
  icon: '∑',
  accent: 'cyan',
  description: 'Combine two numbers',
  fields: [
    { name: 'operation', type: 'select', default: 'add', options: [...] },
    { name: 'precision', type: 'number', default: 2, min: 0, max: 10 },
  ],
  handles: [
    { name: 'a', type: 'target', position: 'left', label: 'a' },
    { name: 'b', type: 'target', position: 'left', label: 'b' },
    { name: 'result', type: 'source', position: 'right' },
  ],
}
```

A single `BaseNode` component renders any config: the chrome, the fields
(through `NodeField`, which is the one place a control type is implemented),
the sockets and their spacing, and the binding of every field to the store.
The palette is generated from the same list, so a new entry appears there
without anyone editing the palette.

### Handles may be a function of state

This is what makes the abstraction more than a convenience. Both `fields`
and `handles` may be a *function* of `{ id, data }`:

```javascript
// The Text node grows one input socket per {{variable}} in its template.
handles: ({ data }) => [
  ...extractVariables(data?.text).map((name) => ({
    name, type: 'target', position: 'left', label: name,
  })),
  { name: 'output', type: 'source', position: 'right' },
],
```

A node's shape therefore follows its own content as the user types. The
consequence is that sockets can *disappear*, so `BaseNode` reports its live
socket set to the store, which prunes any edge attached to a socket that no
longer exists. Without that, deleting a variable would leave an edge hanging
in empty space.

### Adding a node type

Two files, no components:

1. A config object in `frontend/src/nodes/nodeConfigs.js` — appearance.
2. A `register(NodeSpec(...))` call in `backend/app/nodes/handlers.py` —
   behaviour.

The two are deliberately separate. The frontend owns what a node *looks
like*; the backend owns what it *does* and what it *requires*. Neither
imports the other, and the contract between them is the handle names.

---

## The graph layer

### Why Kahn's algorithm

Detecting a cycle could be done with a depth-first search alone. Kahn's
algorithm is used instead because it answers four questions in one pass:

1. **Is it acyclic?** Yes exactly when the sort covers every node.
2. **In what order do the nodes run?** The sort itself.
3. **How deep is the pipeline?** Each node's level is one past its deepest
   predecessor; the maximum is the longest path.
4. **Where does each node belong on screen?** Those same levels are the
   columns the auto-layout uses.

A DFS would answer only the first. Getting four answers for the cost of one
pass is the reason for the choice.

It runs in *O(V + E)*: each node enters the queue once, and each edge is
relaxed once.

### Naming the cycle

Kahn's algorithm reports *that* a cycle exists and leaves behind the set of
nodes it could not place — but it does not say which nodes form the loop, and
that set includes everything *downstream* of a cycle as well as the cycle
itself.

So a second pass runs a colour-marking DFS **restricted to the unplaced
nodes**. Nodes on the current path are grey; when the walk reaches a grey
node, the slice of the path from that node onward is a cycle. Cycles are
de-duplicated by membership, so the same loop found from two entry points is
reported once.

It is written **iteratively**, with an explicit stack of
`(node, neighbour-iterator)` frames, rather than recursively. A 5,000-node
chain would exceed Python's recursion limit; there is a test that builds
exactly that.

### Two passes, not one

Structure and semantics are separate functions because they take different
inputs and answer different questions.

`analyse` sees only ids and edges — it does not know what a "Math node" is,
and it does not need to. `validate` consults the node registry and is the only
place that knows a Math node needs both `a` and `b`.

Keeping them apart means the graph algorithms are testable without any node
types in play, and node rules are testable without constructing interesting
graph shapes.

---

## The execution engine

### One pass is enough

Because the nodes arrive in topological order, every predecessor of a node has
already run by the time the node does. There is no scheduler, no work queue,
no re-entry, and no fixed-point iteration — the engine is a `for` loop over
the sorted order.

### Branching, for free

A handler returns a dictionary of `socket → value` and **may leave a socket
out**:

```python
def run_condition(data, inputs):
    taken = evaluate_truthy(data.get('expression', ''), {'value': inputs.get('value')})
    return {'true': inputs['value']} if taken else {'false': inputs['value']}
```

The engine reads a missing socket as "nothing flowed down this path". A node
whose every incoming edge came up empty is marked **skipped** rather than run
with missing inputs — and because the skip set is built as the pass proceeds,
a skip propagates to the entire subtree below it automatically.

The alternative — a separate control-flow mechanism layered over dataflow —
would need its own scheduler and its own correctness argument. This needs
neither.

### Failure is contained

Three kinds of failure are handled distinctly:

| Failure | Result |
|---|---|
| Validation errors before the run | Nothing executes; the issues are returned |
| A handler raises `NodeExecutionError` | That node is `error`; its subtree is skipped; the run reports `error` |
| A handler raises anything else | Caught, reported as that node's error — a bug in one handler cannot take down the API |

---

## The expression sandbox

The Condition node accepts a typed expression. `eval` would hand whoever opens
the app the entire Python runtime, so the expression is parsed to an AST and
walked by hand. Only these node types execute: constants, names the caller
supplied, binary and unary operators, boolean operators, comparisons, calls to
a fixed list of pure functions, list/tuple literals, and conditional
expressions.

Everything else raises `ExpressionError`. There is no attribute access
(so no `().__class__.__bases__`), no subscripting, no imports, no lambdas, and
no name resolution beyond what the caller passes in. `test_expressions.py`
attempts ten escapes and asserts each is refused.

---

## Frontend state

One Zustand store holds the nodes, the edges, the history and the last
backend result. Every action that changes the graph calls `commit()` first,
which is what makes undo work uniformly without any component knowing that
history exists.

### Undo/redo

Whole `{nodes, edges}` snapshots, capped at 50. A pipeline that fits on a
canvas is small enough that 50 copies cost less than maintaining a correct
inverse operation for every action — and an inverse that is subtly wrong
produces corruption that is very hard to trace.

Two details matter:

- **A drag snapshots on its first `position` change**, while `dragging` is
  still true. Snapshotting at drag *end* would capture the node where the drag
  had already left it, and undo would do nothing.
- **Only field edits coalesce.** Typing fires an action per keystroke, so
  consecutive edits to the same field within 700 ms collapse into one step.
  Discrete actions — adding a node, connecting an edge — never coalesce, even
  in quick succession, because each one is something the user deliberately
  did. (An earlier version coalesced on any repeated tag, which silently
  merged three separate node additions into one undo step; `store.test.js`
  now pins this.)

### Client-side graph checks

`lib/graph.js` mirrors the backend's topological pass. It exists because the
canvas needs answers faster than a round trip:

- `wouldCreateCycle` runs on every hovered connection, so a cycle cannot be
  drawn in the first place. It walks forward from the prospective target: if
  the walk reaches the source, the edge would close a loop.
- `topologicalSort` feeds the auto-layout.

The backend remains the authority. The client check is a better experience,
not a substitute — a pipeline imported from a file still gets validated
server-side.

---

## Auto-layout

Topological levels are the columns: every node sits one column right of its
deepest predecessor, so no edge points backwards. Within a column, nodes are
ordered by the mean row of their already-placed parents, which keeps edge
crossings down without a full Sugiyama pass. Columns are centred against the
tallest one so the diagram balances on a horizontal axis.

A cyclic graph is **left exactly as it is**. There is no correct column order
for a loop, and rearranging the canvas would hide the very thing the user
needs to see.

---

## Wire format

Two different shapes leave the canvas:

| Shape | Contains | Used for |
|---|---|---|
| `toApiPayload` | ids, types, data, edge endpoints | API requests |
| `toDocument` | the above **plus positions**, a version and a name | Saved `.json` files |

React Flow decorates nodes with positions, measured widths, z-index and
selection state. None of it is modelled by the API — sending it would couple
the API to the renderer. A saved file, by contrast, must reopen the canvas as
it was left, so it keeps positions and nothing else.

`fromDocument` validates on the way back in, because the input is a file the
user picked: it rejects malformed documents with a message a person can act
on, drops edges whose endpoints are missing, reports how many were dropped,
and rebuilds the per-type id counters so ids issued after a load cannot
collide with what was loaded.

---

## Testing strategy

| Layer | Tests | Focus |
|---|---|---|
| `core/graph.py` | 36 | Graph shapes: chains, rings, diamonds, self-loops, disconnected components, malformed input |
| `core/validation.py` | 23 | One test per rule, plus severity ordering |
| `core/engine.py` + handlers | 58 | End-to-end runs, branching, skip propagation, per-handler behaviour |
| `core/expressions.py` | 42 | The supported subset, and ten attempted escapes |
| `api/routes.py` | 22 | HTTP contract, backwards compatibility, CORS |
| Frontend | 94 | Graph utilities, layout, serialisation round-trips, store behaviour |

The backend suite runs in well under a second, which is deliberate: a suite
that is slow is a suite that gets run less.
