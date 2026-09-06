// lib/serialize.js
// The pipeline file format, and the conversions on either side of it.
//
// Two different shapes leave the canvas:
//   toApiPayload   what the backend models — the graph, without the drawing
//   toDocument     what a saved .json file holds — the graph *and* enough
//                  view state to reopen the canvas exactly as it was left
// --------------------------------------------------

export const FILE_VERSION = 1;

// React Flow decorates nodes and edges with view state the API never reads
// (positions, z-index, measured widths, selection). Sending it would couple
// the API to the renderer, so only the modelled fields go over the wire.
export const toApiPayload = (nodes, edges) => ({
  nodes: nodes.map(({ id, type, data }) => ({ id, type, data })),
  edges: edges.map(({ id, source, target, sourceHandle, targetHandle }) => ({
    id,
    source,
    target,
    sourceHandle,
    targetHandle,
  })),
});

export const toDocument = (nodes, edges, meta = {}) => ({
  version: FILE_VERSION,
  savedAt: new Date().toISOString(),
  name: meta.name || 'Untitled pipeline',
  nodes: nodes.map(({ id, type, position, data }) => ({ id, type, position, data })),
  edges: edges.map(({ id, source, target, sourceHandle, targetHandle }) => ({
    id,
    source,
    target,
    sourceHandle,
    targetHandle,
  })),
});

export class InvalidDocumentError extends Error {}

// Rebuilds the highest node counter seen per type, so ids issued after a
// load continue the sequence instead of colliding with what was loaded.
export const deriveNodeIds = (nodes) => {
  const counters = {};

  nodes.forEach((node) => {
    const match = /^(.*)-(\d+)$/.exec(node.id || '');
    if (!match) return;
    const [, prefix, number] = match;
    counters[prefix] = Math.max(counters[prefix] || 0, Number(number));
  });

  return counters;
};

/**
 * Parses a saved document back into canvas state.
 *
 * Throws `InvalidDocumentError` with a message meant for the user, because
 * the input is a file they picked and the failure has to be explainable.
 */
export const fromDocument = (raw) => {
  let parsed = raw;

  if (typeof raw === 'string') {
    try {
      parsed = JSON.parse(raw);
    } catch (error) {
      throw new InvalidDocumentError('That file is not valid JSON.');
    }
  }

  if (!parsed || typeof parsed !== 'object') {
    throw new InvalidDocumentError('That file does not contain a pipeline.');
  }

  if (!Array.isArray(parsed.nodes) || !Array.isArray(parsed.edges)) {
    throw new InvalidDocumentError(
      'That file is missing its "nodes" or "edges" list.'
    );
  }

  if (parsed.version !== undefined && parsed.version > FILE_VERSION) {
    throw new InvalidDocumentError(
      `That file was saved by a newer version (v${parsed.version}) of the app.`
    );
  }

  const nodes = parsed.nodes.map((node, index) => {
    if (!node || typeof node.id !== 'string') {
      throw new InvalidDocumentError(`Node ${index + 1} has no id.`);
    }
    return {
      id: node.id,
      type: node.type,
      // A document written by hand may omit positions; stacking them at the
      // origin is recoverable, since auto-layout is one click away.
      position: node.position || { x: 0, y: 0 },
      data: node.data || {},
    };
  });

  const known = new Set(nodes.map((node) => node.id));
  const edges = parsed.edges
    .filter((edge) => edge && known.has(edge.source) && known.has(edge.target))
    .map((edge, index) => ({
      id: edge.id || `edge-${index + 1}`,
      source: edge.source,
      target: edge.target,
      sourceHandle: edge.sourceHandle ?? null,
      targetHandle: edge.targetHandle ?? null,
    }));

  return {
    name: typeof parsed.name === 'string' ? parsed.name : 'Untitled pipeline',
    nodes,
    edges,
    nodeIDs: deriveNodeIds(nodes),
    // Reported so the UI can tell the user edges were dropped rather than
    // letting them wonder where their connections went.
    droppedEdges: parsed.edges.length - edges.length,
  };
};

// Triggers a browser download of the document as a .json file.
export const downloadDocument = (document_, filename = 'pipeline.json') => {
  const blob = new Blob([JSON.stringify(document_, null, 2)], {
    type: 'application/json',
  });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');

  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
};
