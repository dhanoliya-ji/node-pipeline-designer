# API reference

Base URL in development: `http://localhost:8000`
Interactive docs: `http://localhost:8000/docs`

All request and response bodies are JSON.

---

## Common types

### Pipeline (request body)

```json
{
  "nodes": [
    { "id": "customInput-1", "type": "customInput", "data": { "inputValue": "Ada" } }
  ],
  "edges": [
    {
      "id": "e1",
      "source": "customInput-1",
      "target": "text-1",
      "sourceHandle": "customInput-1-value",
      "targetHandle": "text-1-name"
    }
  ]
}
```

Handle ids are prefixed with their node's id (`${nodeId}-${handleName}`),
which is what React Flow emits. The API strips the prefix, so a bare handle
name is accepted too. Unknown fields on a node or edge are ignored, so the
canvas's view state can be sent without stripping it — though the frontend
strips it anyway.

### Issue

```json
{
  "code": "MISSING_REQUIRED_INPUT",
  "severity": "error",
  "message": "'math-1' needs its 'b' input connected.",
  "node_id": "math-1",
  "edge_id": null
}
```

`severity` is `error`, `warning` or `info`. Issues are returned sorted by
severity, errors first.

---

## `GET /`

Service identity.

```json
{ "name": "Node Pipeline Designer API", "version": "1.0.0", "docs": "/docs" }
```

## `GET /health`

```json
{ "status": "ok", "node_types": 9 }
```

## `GET /nodes`

The node types the engine can execute.

```json
[
  {
    "type": "math",
    "label": "Math",
    "description": "Arithmetic on two numeric inputs.",
    "inputs": ["a", "b"],
    "outputs": ["result"],
    "executable": true
  }
]
```

A node type whose sockets depend on its data (Text, Merge) reports an empty
`inputs` list here, because the answer depends on a specific node's state.

---

## `POST /pipelines/parse`

Structure and validation in one call. This is the endpoint the original build
shipped; `num_nodes`, `num_edges` and `is_dag` keep their names and meanings,
and everything else is additive.

**Response**

| Field | Type | Meaning |
|---|---|---|
| `num_nodes` | int | Nodes submitted |
| `num_edges` | int | Edges submitted |
| `is_dag` | bool | True when the topological sort covered every node |
| `cycles` | string[][] | Each cycle, as the list of node ids on it |
| `topological_order` | string[] | Execution order; partial when cyclic |
| `depth` | int | Longest path in nodes; `0` when cyclic |
| `entry_points` | string[] | Nodes with no incoming edges |
| `exit_points` | string[] | Nodes with no outgoing edges |
| `isolated_nodes` | string[] | Nodes with no edges at all |
| `issues` | Issue[] | Everything validation found |

**Example**

```bash
curl -X POST http://localhost:8000/pipelines/parse \
  -H 'Content-Type: application/json' \
  -d '{"nodes":[{"id":"a"},{"id":"b"}],"edges":[{"source":"a","target":"b"},{"source":"b","target":"a"}]}'
```

```json
{
  "num_nodes": 2,
  "num_edges": 2,
  "is_dag": false,
  "cycles": [["a", "b"]],
  "topological_order": [],
  "depth": 0,
  "entry_points": [],
  "exit_points": [],
  "isolated_nodes": [],
  "issues": [
    { "code": "CYCLE", "severity": "error", "node_id": "a",
      "message": "This node sits on a cycle: a -> b -> a." },
    { "code": "CYCLE", "severity": "error", "node_id": "b",
      "message": "This node sits on a cycle: a -> b -> a." }
  ]
}
```

---

## `POST /pipelines/validate`

Validation without the structural statistics.

```json
{
  "is_dag": true,
  "is_valid": false,
  "issues": [ ... ],
  "topological_order": ["customInput-1", "text-1", "customOutput-1"]
}
```

`is_valid` is true when the pipeline is a DAG **and** carries no `error`-level
issues. Warnings do not make a pipeline invalid.

---

## `POST /pipelines/execute`

Runs the pipeline.

**Query parameters**

| Name | Default | Meaning |
|---|---|---|
| `strict` | `true` | Refuse to run a pipeline with validation errors. `false` runs whatever is runnable. |

**Response**

| Field | Type | Meaning |
|---|---|---|
| `status` | `ok` \| `error` | `error` if refused, or if any node failed |
| `steps` | ExecutionStep[] | One per node, in execution order |
| `outputs` | object | Keyed by each Output node's `outputName` |
| `duration_ms` | float | Wall-clock for the whole run |
| `issues` | Issue[] | The validation report for the same pipeline |

**ExecutionStep**

| Field | Meaning |
|---|---|
| `node_id`, `node_type` | Which node |
| `status` | `ok`, `skipped` or `error` |
| `outputs` | What it produced, per output socket |
| `duration_ms` | Wall-clock for that node |
| `message` | Why it was skipped, or how it failed |

A `skipped` node is not a failure. It means no value reached it — almost
always because an upstream branch was not taken.

**Example**

```bash
curl -X POST http://localhost:8000/pipelines/execute \
  -H 'Content-Type: application/json' \
  -d @examples/greeting.json
```

```json
{
  "status": "ok",
  "outputs": { "greeting": "Hello, Ada!" },
  "duration_ms": 0.21,
  "steps": [
    { "node_id": "customInput-1", "status": "ok", "outputs": { "value": "Ada" } },
    { "node_id": "text-1", "status": "ok", "outputs": { "output": "Hello, Ada!" } },
    { "node_id": "customOutput-1", "status": "ok", "outputs": { "value": "Hello, Ada!" } }
  ],
  "issues": []
}
```

**Errors**

| Status | When |
|---|---|
| `413` | The pipeline exceeds `NPD_MAX_NODES` / `NPD_MAX_EDGES` |
| `422` | The body does not match the schema |

---

## Issue codes

| Code | Severity | Raised when |
|---|---|---|
| `CYCLE` | error | The node sits on a cycle |
| `SELF_LOOP` | error | A node is connected to itself |
| `DANGLING_EDGE` | error | An edge references a node that is not present |
| `DUPLICATE_NODE_ID` | error | Two nodes share an id |
| `UNKNOWN_SOURCE_HANDLE` | error | An edge leaves an output that does not exist |
| `UNKNOWN_TARGET_HANDLE` | error | An edge lands on an input that does not exist |
| `AMBIGUOUS_INPUT` | error | Two or more edges feed one single-value input |
| `MISSING_REQUIRED_INPUT` | error | A mandatory input has nothing connected |
| `MISSING_URL` | error | An API node has no URL |
| `UNCONNECTED_VARIABLE` | warning | A Text node's `{{variable}}` has nothing connected |
| `ISOLATED_NODE` | warning | A node has no edges at all |
| `NO_OUTPUT_NODE` | warning | The pipeline has no Output node |
| `UNKNOWN_NODE_TYPE` | warning | No handler is registered for the node's type |
| `EMPTY_PIPELINE` | info | No nodes were submitted |

---

## Node reference

| Type | Inputs | Outputs | Behaviour |
|---|---|---|---|
| `customInput` | — | `value` | Emits its configured value; coerced to a number when its type is Number |
| `customOutput` | `value`* | `value` | Collected into the run's `outputs` under its `outputName` |
| `text` | one per `{{variable}}` | `output` | Substitutes each variable; an unconnected one is left as `{{name}}` so the gap is visible |
| `llm` | `system`, `prompt`* | `response` | **Simulated.** Returns a deterministic, clearly-labelled echo |
| `math` | `a`*, `b`* | `result` | add / subtract / multiply / divide, rounded to `precision` |
| `filter` | `input`* | `pass`, `fail` | Routes to exactly one branch by contains / equals / startsWith / regex |
| `condition` | `value`* | `true`, `false` | Routes by a sandboxed boolean expression over `value` |
| `merge` | `input_1..n` | `merged` | concat / array / object |
| `api` | `body` | `response`, `error` | HTTP call; **disabled unless `NPD_ALLOW_OUTBOUND_HTTP=true`** |

`*` marks a required input.

---

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `NPD_CORS_ORIGIN_REGEX` | any localhost port | Which origins may call the API |
| `NPD_MAX_NODES` | `2000` | Size guard for execution |
| `NPD_MAX_EDGES` | `8000` | Size guard for execution |
| `NPD_ALLOW_OUTBOUND_HTTP` | `false` | Lets the API node make real requests |
| `NPD_HTTP_TIMEOUT_CEILING` | `30` | Upper bound on an API node's timeout |

Outbound HTTP is off by default because an endpoint that fetches any URL a
visitor supplies is a request-forgery hole. With it off, the API node reports
the call it *would* have made on its `error` socket, so branch wiring can
still be built and tested.
