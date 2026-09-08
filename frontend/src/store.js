// store.js
// The single source of truth for the canvas: the graph, the history stack,
// and the results of the last validate or run.
//
// Every structural change goes through an action here, and every action that
// changes the graph calls `commit` first, which is what makes undo work
// uniformly without each component knowing anything about history.
// --------------------------------------------------

import { create } from 'zustand';
import {
  addEdge,
  applyNodeChanges,
  applyEdgeChanges,
  MarkerType,
} from 'reactflow';

import { autoLayout } from './lib/layout';
import { wouldCreateCycle } from './lib/graph';
import { clearPipeline, loadPipeline, savePipeline } from './lib/storage';
import { deriveNodeIds } from './lib/serialize';

const HISTORY_LIMIT = 50;

// How long two consecutive edits to the same field fold into one undo step.
// Typing fires an action per keystroke; without this, undo would walk back
// one character at a time.
//
// Only field edits coalesce. Discrete actions — adding a node, connecting an
// edge — are each their own step even when they happen in quick succession,
// because each one is something the user deliberately did.
const COALESCE_MS = 700;
const COALESCING_TAG = /^field:/;

const edgeOptions = {
  type: 'smoothstep',
  animated: true,
  markerEnd: { type: MarkerType.ArrowClosed, height: 18, width: 18 },
};

const snapshot = (state) => ({ nodes: state.nodes, edges: state.edges });

const emptyResults = {
  issues: [],
  stats: null,
  run: null,
  apiError: null,
};

export const useStore = create((set, get) => ({
  nodes: [],
  edges: [],
  nodeIDs: {},
  pipelineName: 'Untitled pipeline',

  // Undo/redo. Both stacks hold whole {nodes, edges} snapshots: a pipeline
  // that fits on a canvas is small enough that storing 50 of them costs less
  // than maintaining a correct inverse for every action.
  past: [],
  future: [],
  lastTag: null,
  lastCommitAt: 0,

  // Results of the last backend call.
  ...emptyResults,
  isBusy: false,

  // ---- History --------------------------------------------------------

  commit: (tag = null) => {
    const state = get();
    const now = Date.now();

    // Successive edits to the same field collapse into the step before them.
    if (
      tag &&
      COALESCING_TAG.test(tag) &&
      tag === state.lastTag &&
      now - state.lastCommitAt < COALESCE_MS
    ) {
      set({ lastCommitAt: now });
      return;
    }

    set({
      past: [...state.past, snapshot(state)].slice(-HISTORY_LIMIT),
      future: [],
      lastTag: tag,
      lastCommitAt: now,
    });
  },

  undo: () => {
    const state = get();
    if (!state.past.length) return;

    const previous = state.past[state.past.length - 1];
    set({
      ...previous,
      past: state.past.slice(0, -1),
      future: [snapshot(state), ...state.future].slice(0, HISTORY_LIMIT),
      lastTag: null,
      ...emptyResults,
    });
  },

  redo: () => {
    const state = get();
    if (!state.future.length) return;

    const [next, ...rest] = state.future;
    set({
      ...next,
      past: [...state.past, snapshot(state)].slice(-HISTORY_LIMIT),
      future: rest,
      lastTag: null,
      ...emptyResults,
    });
  },

  canUndo: () => get().past.length > 0,
  canRedo: () => get().future.length > 0,

  // ---- Identity -------------------------------------------------------

  getNodeID: (type) => {
    const nodeIDs = { ...get().nodeIDs };
    nodeIDs[type] = (nodeIDs[type] || 0) + 1;
    set({ nodeIDs });
    return `${type}-${nodeIDs[type]}`;
  },

  // ---- Graph mutations ------------------------------------------------

  addNode: (node) => {
    get().commit('add-node');
    set({ nodes: [...get().nodes, node], ...emptyResults });
  },

  onNodesChange: (changes) => {
    // A drag produces a stream of position changes. The snapshot has to be
    // taken on the first one, before anything moves, or undo would restore
    // the node to where the drag had already carried it.
    const startsDrag = changes.some(
      (change) => change.type === 'position' && change.dragging === true
    );
    const removes = changes.some((change) => change.type === 'remove');

    if (removes) get().commit('remove-node');
    else if (startsDrag) get().commit('move-node');

    set({
      nodes: applyNodeChanges(changes, get().nodes),
      ...(removes ? emptyResults : {}),
    });
  },

  onEdgesChange: (changes) => {
    const removes = changes.some((change) => change.type === 'remove');
    if (removes) get().commit('remove-edge');

    set({
      edges: applyEdgeChanges(changes, get().edges),
      ...(removes ? emptyResults : {}),
    });
  },

  onConnect: (connection) => {
    get().commit('connect');
    set({
      edges: addEdge({ ...connection, ...edgeOptions }, get().edges),
      ...emptyResults,
    });
  },

  // Refuses a connection that would close a loop, before it is ever drawn.
  // The backend would catch it too, but a pipeline the user cannot even draw
  // into an invalid state is a better experience than one that explains the
  // mistake afterwards.
  isValidConnection: (connection) =>
    !wouldCreateCycle(get().edges, connection.source, connection.target),

  updateNodeField: (nodeId, fieldName, fieldValue) => {
    get().commit(`field:${nodeId}:${fieldName}`);
    set({
      nodes: get().nodes.map((node) =>
        node.id === nodeId
          ? { ...node, data: { ...node.data, [fieldName]: fieldValue } }
          : node
      ),
      ...emptyResults,
    });
  },

  // Drops edges pointing at handles a node no longer renders. Nodes with
  // data-driven handles (Text, Merge) call this when their handle set
  // shrinks, which keeps edges from dangling in empty space.
  //
  // Deliberately does not commit: it is a consequence of the edit that
  // already committed, and undo should reverse both together.
  pruneNodeHandles: (nodeId, validHandleIds) => {
    const valid = new Set(validHandleIds);
    const isOrphaned = (edge) =>
      (edge.source === nodeId && edge.sourceHandle && !valid.has(edge.sourceHandle)) ||
      (edge.target === nodeId && edge.targetHandle && !valid.has(edge.targetHandle));

    const edges = get().edges;
    const remaining = edges.filter((edge) => !isOrphaned(edge));
    if (remaining.length !== edges.length) set({ edges: remaining });
  },

  deleteSelected: () => {
    const { nodes, edges } = get();
    const doomed = new Set(nodes.filter((node) => node.selected).map((n) => n.id));
    const selectedEdges = edges.filter((edge) => edge.selected).map((e) => e.id);
    if (!doomed.size && !selectedEdges.length) return;

    get().commit('delete');
    const dropped = new Set(selectedEdges);
    set({
      nodes: nodes.filter((node) => !doomed.has(node.id)),
      edges: edges.filter(
        (edge) =>
          !dropped.has(edge.id) &&
          !doomed.has(edge.source) &&
          !doomed.has(edge.target)
      ),
      ...emptyResults,
    });
  },

  duplicateSelected: () => {
    const { nodes, getNodeID } = get();
    const selected = nodes.filter((node) => node.selected);
    if (!selected.length) return;

    get().commit('duplicate');
    const copies = selected.map((node) => ({
      ...node,
      id: getNodeID(node.type),
      position: { x: node.position.x + 40, y: node.position.y + 40 },
      data: { ...node.data },
      selected: false,
    }));

    // The copies keep their own data, but not their id, so the `id` field
    // inside data (used by the Input/Output name defaults) is refreshed.
    copies.forEach((copy) => {
      copy.data.id = copy.id;
    });

    set({
      nodes: [...nodes.map((n) => ({ ...n, selected: false })), ...copies],
      ...emptyResults,
    });
  },

  applyAutoLayout: () => {
    const { nodes, edges } = get();
    const { nodes: laid, changed } = autoLayout(nodes, edges);
    if (!changed) return false;

    get().commit('layout');
    set({ nodes: laid });
    return true;
  },

  clear: () => {
    if (!get().nodes.length && !get().edges.length) return;
    get().commit('clear');
    set({ nodes: [], edges: [], nodeIDs: {}, ...emptyResults });
    clearPipeline();
  },

  // ---- Documents ------------------------------------------------------

  loadDocument: ({ nodes, edges, name, nodeIDs }) => {
    get().commit('load');
    set({
      nodes,
      edges,
      nodeIDs: nodeIDs || deriveNodeIds(nodes),
      pipelineName: name || 'Untitled pipeline',
      ...emptyResults,
    });
  },

  setPipelineName: (pipelineName) => set({ pipelineName }),

  saveToBrowser: () => {
    const { nodes, edges, pipelineName } = get();
    return savePipeline(nodes, edges, { name: pipelineName });
  },

  restoreFromBrowser: () => {
    const document_ = loadPipeline();
    if (!document_ || !document_.nodes.length) return false;
    get().loadDocument(document_);
    return true;
  },

  // ---- Backend results -------------------------------------------------

  setBusy: (isBusy) => set({ isBusy }),

  setStats: (stats) =>
    set({ stats, issues: stats?.issues || [], run: null, apiError: null }),

  setValidation: (report) =>
    set({ issues: report?.issues || [], run: null, apiError: null }),

  setRun: (run) =>
    set({ run, issues: run?.issues || [], apiError: null }),

  setApiError: (apiError) => set({ apiError, run: null }),

  clearResults: () => set({ ...emptyResults }),
}));

// Groups the current issues by the node they belong to, so a node can look
// up its own without every node scanning the whole list.
export const selectIssuesByNode = (state) => {
  const byNode = {};
  state.issues.forEach((issue) => {
    if (!issue.node_id) return;
    (byNode[issue.node_id] = byNode[issue.node_id] || []).push(issue);
  });
  return byNode;
};

// The worst severity attached to a node, which is what its outline shows.
export const severityFor = (issues = []) => {
  if (issues.some((issue) => issue.severity === 'error')) return 'error';
  if (issues.some((issue) => issue.severity === 'warning')) return 'warning';
  return null;
};
