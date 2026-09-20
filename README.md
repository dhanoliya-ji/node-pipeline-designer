# Node Pipeline Designer

A visual editor for node pipelines, with the two things most node editors
leave out: it tells you **why** your graph is wrong, and it **runs** it.

Drag nodes onto a canvas, wire them together, and the backend answers three
questions — is this a valid directed acyclic graph, is it wired correctly, and
what happens when it executes.

<p align="center">
  <img alt="Python 3.10+" src="https://img.shields.io/badge/python-3.10%2B-3776ab">
  <img alt="React 18" src="https://img.shields.io/badge/react-18-61dafb">
  <img alt="FastAPI" src="https://img.shields.io/badge/fastapi-0.116-009688">
  <img alt="275 tests" src="https://img.shields.io/badge/tests-275-16a34a">
  <img alt="92% coverage" src="https://img.shields.io/badge/coverage-92%25-16a34a">
</p>

---

## Contents

- [What it does](#what-it-does)
- [Why it exists](#why-it-exists)
- [Quick start](#quick-start)
- [A first pipeline](#a-first-pipeline)
- [The node library](#the-node-library)
- [How it works](#how-it-works)
- [Adding a node type](#adding-a-node-type)
- [Performance](#performance)
- [Testing](#testing)
- [Project layout](#project-layout)
- [Configuration](#configuration)
- [Documentation](#documentation)

---

## What it does

**Builds pipelines visually.** Drag from a searchable palette, connect
sockets, drag to rearrange. Nine node types covering input, templating,
arithmetic, filtering, branching, merging, HTTP and LLM calls.

**Refuses to let you draw a cycle.** A connection that would close a loop is
rejected as you drag it, not after you submit.

**Explains what is wrong, precisely.** Fourteen validation rules across two
layers — structural (cycles, self-loops, dangling edges) and semantic (missing
required inputs, sockets that do not exist, two edges feeding one input,
templates referring to variables nothing supplies, nodes stranded on the
canvas). Every issue carries a severity and the id of the element responsible,
so clicking it in the results panel selects and centres that node.

**Runs the pipeline.** A single-pass topological engine executes the graph and
reports, per node, what it produced, how long it took, or why it was skipped.
Conditional branches route down exactly one path, and the untaken branch's
whole subtree is marked *skipped* rather than failed.

**Behaves like a tool you would actually use.** Undo/redo, autosave,
save/load, JSON import/export, one-key auto-layout by dependency order,
keyboard shortcuts, live backend-health indicator, light and dark themes.

---

## Why it exists

A pipeline has to be a **directed acyclic graph**. *Directed* because data
flows one way; *acyclic* because a stage that ultimately depends on its own
output can never start — there is no order in which to run it.

A visual canvas makes a cycle trivially easy to create (three connections in a
triangle) and genuinely hard to spot, because the loop can span a part of the
diagram you are not looking at. And being acyclic is only half the problem: a
Math node with one operand connected is a perfect DAG and complete nonsense.

So the project does the structural check *and* the semantic one, and then runs
the thing so you can see what it actually does.

The full reasoning, objectives, requirements and evaluation are in
**[docs/PROBLEM_STATEMENT.pdf](docs/PROBLEM_STATEMENT.pdf)**.

---

## Quick start

### With Docker

```bash
docker compose up --build
```

Frontend at <http://localhost:3000>, API at <http://localhost:8000>.

### Without Docker

**Backend** — Python 3.10 or newer:

```bash
cd backend
python -m venv .venv

# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 8000
```

The API is then on <http://localhost:8000>, with interactive docs at
<http://localhost:8000/docs>.

**Frontend** — Node 18 or newer, in a second terminal:

```bash
cd frontend
npm install
npm start
```

Open <http://localhost:3000>.

> The app runs without the backend — you can still draw, save and export. The
> header shows **API offline**, and Validate and Run report that they cannot
> reach it.

---

## A first pipeline

Three nodes, thirty seconds:

1. Drag an **Input** onto the canvas. Set its value to `Ada`.
2. Drag a **Text** node. Type `Hello, {{name}}!` into it — a socket named
   `name` appears on its left edge as you type.
3. Drag an **Output** node.
4. Connect Input → `name`, and Text → Output.
5. Press **Run**.

The results panel shows `greeting: "Hello, Ada!"` and a per-node breakdown.

Now break it deliberately: connect the Output back to the Input. The canvas
refuses the connection, because it would close a loop.

Four ready-made pipelines are in [`examples/`](examples/) — import any of them
with the **Import** button:

| File | Shows |
|---|---|
| `greeting.json` | The smallest working pipeline |
| `ticket-triage.json` | Branching: one path taken, one skipped |
| `weighted-score.json` | Fan-in, arithmetic, a condition and a merge |
| `broken-on-purpose.json` | Seven validation issues across five rules |

---

## The node library

| Node | Inputs | Outputs | What it does |
|---|---|---|---|
| **Input** | — | `value` | Where a run starts. Text or Number. |
| **Output** | `value` | — | Collected into the run's result under its name. |
| **Text** | one per `{{variable}}` | `output` | Template string. Sockets appear as you type variables. |
| **LLM** | `system`, `prompt` | `response` | Model call — **simulated** in this build. |
| **Math** | `a`, `b` | `result` | Add, subtract, multiply, divide, to a set precision. |
| **Filter** | `input` | `pass`, `fail` | Routes by contains / equals / starts-with / regex. |
| **Condition** | `value` | `true`, `false` | Routes by a sandboxed boolean expression. |
| **Merge** | `input_1..n` | `merged` | Joins 2–6 inputs as text, an array or an object. |
| **API Request** | `body` | `response`, `error` | HTTP call, disabled by default. |

The LLM node returns a deterministic, clearly-labelled echo rather than
calling a provider — this project is about the graph, not about holding your
API key. Wiring a real client means replacing one function body.

---

## How it works

### Kahn's algorithm, used for four things at once

Cycle detection alone could be a depth-first search. Kahn's algorithm is used
because one *O(V + E)* pass answers four questions:

1. **Is it acyclic?** Yes exactly when the topological sort covers every node.
2. **In what order do nodes run?** The sort itself.
3. **How deep is the pipeline?** Each node's level is one past its deepest
   predecessor.
4. **Where does each node go on screen?** Those same levels are the
   auto-layout's columns.

### Naming the cycle, not just reporting one

Kahn's algorithm leaves behind the nodes it could not place — but that set
includes everything *downstream* of a cycle as well as the cycle itself. So a
second, **iterative** colour-marking DFS runs over just those nodes and
extracts the actual loops. Iterative rather than recursive, so a 5,000-node
chain cannot exhaust the stack; there is a test that builds exactly that.

### Branching falls out of the dataflow rule

A handler returns a value per output socket and **may omit one**. An omitted
socket means nothing flowed that way — so a node whose every incoming edge
came up empty is *skipped*, and because skips accumulate as the single pass
proceeds, the skip propagates down the whole subtree for free. No separate
control-flow mechanism, no second scheduler.

### Expressions without handing over the interpreter

The Condition node takes a typed expression. `eval` would give whoever opens
the app the entire Python runtime, so expressions are parsed to an AST and
walked by hand over a whitelisted subset. No attribute access, no subscripting,
no imports, no lambdas, and only a fixed list of pure functions. Ten escape
attempts — `__import__`, `open`, `().__class__`, `exec`, `globals` — are
tested and refused.

Full detail in **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)**.

---

## Adding a node type

Two objects. No components, no JSX, no CSS, no state wiring.

**1. Appearance** — `frontend/src/nodes/nodeConfigs.js`:

```javascript
{
  type: 'uppercase',
  label: 'Uppercase',
  icon: '⇧',
  accent: 'teal',
  description: 'Convert text to upper case',
  handles: [
    { name: 'input',  type: 'target', position: 'left'  },
    { name: 'output', type: 'source', position: 'right' },
  ],
}
```

**2. Behaviour** — `backend/app/nodes/handlers.py`:

```python
def run_uppercase(data, inputs):
    return {'output': _as_text(inputs.get('input')).upper()}

register(NodeSpec(
    type='uppercase',
    label='Uppercase',
    description='Convert text to upper case.',
    inputs=('input',),
    outputs=('output',),
    required_inputs=('input',),
    handler=run_uppercase,
))
```

It now appears in the palette, renders, validates, and executes. The
`handles` list may also be a **function** of the node's own data — which is
how the Text node grows one socket per `{{variable}}` you type.

---

## Performance

The graph layer is *O(V + E)*, and this is measured rather than asserted.
[`notebooks/analysis.ipynb`](notebooks/analysis.ipynb) benchmarks four graph
shapes across two orders of magnitude and fits a power law to each:

| Graph shape | Fitted exponent | R² |
|---|---|---|
| chain | 0.93 | 0.980 |
| layered | 1.01 | 0.997 |
| random DAG | 0.96 | 0.984 |
| ring (fully cyclic) | 0.98 | 0.998 |

An exponent near 1.0 is linear; a quadratic pass would sit near 2.0. In
absolute terms, a 2,000-node pipeline validates in about **10 ms**.

**The notebook earned its place by finding a bug.** The first run showed a
2,000-node ring validating in 38 ms against 9 ms for a random DAG of the same
size. Every node on a cycle was getting an issue whose message named the
*entire* cycle — a `V`-node ring built `V` strings of `V` ids, `O(V²)` inside
an otherwise linear pass. Every unit test used a small graph, so it was
invisible. The message is now built once per cycle and abbreviated past eight
nodes: the same case now takes 9.6 ms, and
`test_a_long_cycle_abbreviates_its_message` keeps it that way.

Regenerate the measurements:

```bash
cd backend && python -m benchmarks.bench_graph
```

---

## Testing

**275 tests.** Backend 92% statement coverage.

```bash
# Backend — 181 tests, under a second
cd backend
pytest -q --cov=app --cov-report=term-missing

# Frontend — 94 tests
cd frontend
npm run test:ci
```

| Suite | Tests | Covers |
|---|---|---|
| `test_graph.py` | 36 | Chains, rings, diamonds, self-loops, disconnected components, malformed input |
| `test_engine.py` | 58 | End-to-end runs, branching, skip propagation, every handler |
| `test_expressions.py` | 42 | The supported subset, plus ten attempted sandbox escapes |
| `test_validation.py` | 23 | One test per rule, plus severity ordering |
| `test_api.py` | 22 | HTTP contract, backwards compatibility, CORS |
| Frontend | 94 | Graph utilities, layout, serialisation round-trips, store and undo/redo |

CI runs the backend on Python 3.10, 3.11 and 3.12, the frontend on Node 20,
builds both Docker images, and smoke-tests the API container.

---

## Project layout

```
node-pipeline-designer/
├── backend/
│   ├── app/
│   │   ├── main.py              FastAPI app factory
│   │   ├── config.py            Environment-driven settings
│   │   ├── api/routes.py        HTTP adapters — no logic
│   │   ├── core/
│   │   │   ├── graph.py         Kahn's algorithm, cycle DFS, shape metrics
│   │   │   ├── validation.py    Semantic rules → Issue[]
│   │   │   ├── engine.py        Single-pass topological execution
│   │   │   └── expressions.py   Sandboxed AST evaluator
│   │   ├── nodes/               Registry + one handler per node type
│   │   └── schemas/             Pydantic wire format
│   ├── tests/                   181 tests
│   ├── benchmarks/              Performance harness
│   └── Dockerfile
│
├── frontend/
│   ├── src/
│   │   ├── App.js               Shell
│   │   ├── store.js             Zustand: graph, history, results
│   │   ├── api/client.js        Every backend call
│   │   ├── components/          BaseNode, Canvas, TopBar, InspectorPanel, …
│   │   ├── nodes/               nodeConfigs.js — the node library, as data
│   │   ├── lib/                 graph · layout · serialize · storage
│   │   └── hooks/               Keyboard shortcuts
│   └── Dockerfile
│
├── docs/
│   ├── PROBLEM_STATEMENT.md/.pdf   Problem, objectives, requirements
│   ├── ARCHITECTURE.md             Design decisions and why
│   └── API.md                      Endpoint reference
│
├── notebooks/analysis.ipynb     Performance and coverage analysis
├── examples/                    Four runnable pipelines
└── docker-compose.yml
```

---

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `REACT_APP_API_URL` | `http://localhost:8000` | Where the frontend looks for the API |
| `NPD_CORS_ORIGIN_REGEX` | any localhost port | Which origins the API accepts |
| `NPD_MAX_NODES` | `2000` | Execution size guard |
| `NPD_MAX_EDGES` | `8000` | Execution size guard |
| `NPD_ALLOW_OUTBOUND_HTTP` | `false` | Lets the API node make real requests |
| `NPD_HTTP_TIMEOUT_CEILING` | `30` | Upper bound on an API node's timeout |

Outbound HTTP is off by default: an endpoint that fetches any URL a visitor
types is a request-forgery hole. With it off, the API node reports the call it
*would* have made on its `error` socket, so branch wiring still works.

---

## Keyboard shortcuts

| Keys | Action |
|---|---|
| `Ctrl/Cmd + Z` | Undo |
| `Ctrl/Cmd + Shift + Z` | Redo |
| `Ctrl/Cmd + S` | Save to browser |
| `Ctrl/Cmd + D` | Duplicate selection |
| `Ctrl/Cmd + Enter` | Run pipeline |
| `Ctrl/Cmd + L` | Auto-layout |
| `Delete` / `Backspace` | Delete selection |

---

## Documentation

| Document | What it covers |
|---|---|
| [docs/PROBLEM_STATEMENT.pdf](docs/PROBLEM_STATEMENT.pdf) | The problem, objectives, requirements, approach and evaluation |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Why the system is built the way it is |
| [docs/API.md](docs/API.md) | Every endpoint, issue code and node type |
| [notebooks/analysis.ipynb](notebooks/analysis.ipynb) | Measured scaling, with charts |

---

## Known limitations

Stated plainly, because a scope that is not bounded is not a scope.

- **The LLM node is simulated.** It returns a labelled echo, not a model
  response.
- **No scheduling or retries.** The engine runs a graph once, in-process.
  It is not an orchestrator.
- **Single user.** No accounts, no collaborative editing; pipelines live in
  the browser or in a JSON file.
- **Outbound HTTP is opt-in** and performs no SSRF filtering beyond a scheme
  check. Do not enable it on an untrusted deployment without adding one.

---

## License

MIT — see [LICENSE](LICENSE).
