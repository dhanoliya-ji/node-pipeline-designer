// lib/graph.js
// Client-side graph analysis.
//
// The backend is the authority on whether a pipeline is valid, but the
// canvas needs answers faster than a round trip: it has to refuse a
// connection that would close a loop *while the user is dragging it*, and it
// has to lay nodes out on demand. Both come from the same topological pass
// implemented here, mirroring `backend/app/core/graph.py`.
// --------------------------------------------------

// Builds adjacency lists from React Flow's node and edge arrays. Edges whose
// endpoints are not on the canvas are ignored, the same way the API does.
const build = (nodes, edges) => {
  const ids = nodes.map((node) => node.id);
  const known = new Set(ids);
  const adjacency = new Map(ids.map((id) => [id, []]));
  const inDegree = new Map(ids.map((id) => [id, 0]));

  edges.forEach((edge) => {
    if (!known.has(edge.source) || !known.has(edge.target)) return;
    adjacency.get(edge.source).push(edge.target);
    inDegree.set(edge.target, inDegree.get(edge.target) + 1);
  });

  return { ids, adjacency, inDegree };
};

// Kahn's algorithm. Returns the order plus each node's level, where a level
// is one past the deepest level among its predecessors. On a cyclic graph
// the order is shorter than the node list, which is how `isDag` decides.
export const topologicalSort = (nodes, edges) => {
  const { ids, adjacency, inDegree } = build(nodes, edges);
  const remaining = new Map(inDegree);
  const queue = ids.filter((id) => remaining.get(id) === 0);
  const levels = new Map(queue.map((id) => [id, 0]));
  const order = [];

  for (let head = 0; head < queue.length; head += 1) {
    const id = queue[head];
    order.push(id);

    adjacency.get(id).forEach((next) => {
      levels.set(next, Math.max(levels.get(next) ?? 0, levels.get(id) + 1));
      remaining.set(next, remaining.get(next) - 1);
      if (remaining.get(next) === 0) queue.push(next);
    });
  }

  return { order, levels, isDag: order.length === ids.length };
};

export const isDag = (nodes, edges) => topologicalSort(nodes, edges).isDag;

// Would adding `source -> target` create a cycle?
//
// Answered by walking forward from `target`: if the walk can reach `source`,
// the new edge closes a loop. Cheaper than re-sorting the whole graph, and
// it runs on every hovered connection, so it is worth the special case.
export const wouldCreateCycle = (edges, source, target) => {
  if (source === target) return true; // A self-loop is a cycle of one.

  const adjacency = new Map();
  edges.forEach((edge) => {
    if (!adjacency.has(edge.source)) adjacency.set(edge.source, []);
    adjacency.get(edge.source).push(edge.target);
  });

  const seen = new Set([target]);
  const stack = [target];

  while (stack.length) {
    const id = stack.pop();
    if (id === source) return true;
    (adjacency.get(id) || []).forEach((next) => {
      if (!seen.has(next)) {
        seen.add(next);
        stack.push(next);
      }
    });
  }

  return false;
};

// Nodes with no edge at all — on the canvas, but not part of the pipeline.
export const findIsolatedNodes = (nodes, edges) => {
  const attached = new Set();
  edges.forEach((edge) => {
    attached.add(edge.source);
    attached.add(edge.target);
  });
  return nodes.filter((node) => !attached.has(node.id)).map((node) => node.id);
};

// A quick local summary for the status bar, so the counts stay live between
// backend calls. Anything requiring node semantics is left to the API.
export const summarise = (nodes, edges) => {
  const { order, levels, isDag: acyclic } = topologicalSort(nodes, edges);
  const depth = levels.size ? Math.max(...levels.values()) + 1 : 0;

  return {
    nodeCount: nodes.length,
    edgeCount: edges.length,
    isDag: acyclic,
    depth: acyclic ? depth : 0,
    isolated: findIsolatedNodes(nodes, edges).length,
    order,
  };
};
