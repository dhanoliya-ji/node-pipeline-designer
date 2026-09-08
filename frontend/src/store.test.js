// Store behaviour, with an emphasis on undo/redo: it touches every action,
// so a regression there is easy to introduce and hard to notice by hand.

import { useStore, severityFor } from './store';

const initial = useStore.getState();

const makeNode = (id, type = 'text', data = {}) => ({
  id,
  type,
  position: { x: 0, y: 0 },
  data: { id, ...data },
});

beforeEach(() => {
  useStore.setState(
    {
      ...initial,
      nodes: [],
      edges: [],
      nodeIDs: {},
      past: [],
      future: [],
      lastTag: null,
      lastCommitAt: 0,
      issues: [],
      stats: null,
      run: null,
      apiError: null,
    },
    true
  );
  window.localStorage.clear();
});

const store = () => useStore.getState();

describe('node ids', () => {
  test('counts up per type', () => {
    expect(store().getNodeID('text')).toBe('text-1');
    expect(store().getNodeID('text')).toBe('text-2');
    expect(store().getNodeID('llm')).toBe('llm-1');
  });

  test('continues the sequence after a document is loaded', () => {
    store().loadDocument({
      nodes: [makeNode('text-4')],
      edges: [],
      name: 'Loaded',
      nodeIDs: { text: 4 },
    });
    expect(store().getNodeID('text')).toBe('text-5');
  });
});

describe('undo and redo', () => {
  test('undo removes a node that was added', () => {
    store().addNode(makeNode('text-1'));
    expect(store().nodes).toHaveLength(1);

    store().undo();
    expect(store().nodes).toHaveLength(0);
  });

  test('redo puts it back', () => {
    store().addNode(makeNode('text-1'));
    store().undo();
    store().redo();
    expect(store().nodes).toHaveLength(1);
  });

  test('several steps unwind in order', () => {
    store().addNode(makeNode('text-1'));
    store().addNode(makeNode('text-2'));
    store().addNode(makeNode('text-3'));

    store().undo();
    expect(store().nodes.map((n) => n.id)).toEqual(['text-1', 'text-2']);
    store().undo();
    expect(store().nodes.map((n) => n.id)).toEqual(['text-1']);
  });

  test('a new action clears the redo stack', () => {
    store().addNode(makeNode('text-1'));
    store().undo();
    store().addNode(makeNode('text-2'));

    expect(store().canRedo()).toBe(false);
    expect(store().nodes.map((n) => n.id)).toEqual(['text-2']);
  });

  test('undo on an empty history does nothing', () => {
    expect(() => store().undo()).not.toThrow();
    expect(store().nodes).toEqual([]);
  });

  test('consecutive edits to one field collapse into a single step', () => {
    // Otherwise undo would walk back one keystroke at a time.
    store().addNode(makeNode('text-1'));
    store().updateNodeField('text-1', 'text', 'h');
    store().updateNodeField('text-1', 'text', 'he');
    store().updateNodeField('text-1', 'text', 'hel');

    store().undo();
    expect(store().nodes[0].data.text).toBeUndefined();
  });

  test('edits to different fields stay separate steps', () => {
    store().addNode(makeNode('text-1'));
    store().updateNodeField('text-1', 'text', 'value');
    store().updateNodeField('text-1', 'other', 'thing');

    store().undo();
    expect(store().nodes[0].data.text).toBe('value');
    expect(store().nodes[0].data.other).toBeUndefined();
  });

  test('history is capped so a long session cannot grow without bound', () => {
    for (let i = 0; i < 80; i += 1) store().addNode(makeNode(`text-${i}`));
    expect(store().past.length).toBeLessThanOrEqual(50);
  });

  test('connecting an edge is undoable', () => {
    store().addNode(makeNode('a'));
    store().addNode(makeNode('b'));
    store().onConnect({ source: 'a', target: 'b' });
    expect(store().edges).toHaveLength(1);

    store().undo();
    expect(store().edges).toHaveLength(0);
  });
});

describe('connection rules', () => {
  test('refuses a connection that would close a loop', () => {
    useStore.setState({
      edges: [
        { id: 'e1', source: 'a', target: 'b' },
        { id: 'e2', source: 'b', target: 'c' },
      ],
    });
    expect(store().isValidConnection({ source: 'c', target: 'a' })).toBe(false);
  });

  test('refuses a node connected to itself', () => {
    expect(store().isValidConnection({ source: 'a', target: 'a' })).toBe(false);
  });

  test('allows a connection that keeps the graph acyclic', () => {
    useStore.setState({ edges: [{ id: 'e1', source: 'a', target: 'b' }] });
    expect(store().isValidConnection({ source: 'b', target: 'c' })).toBe(true);
  });
});

describe('handle pruning', () => {
  test('drops edges attached to a handle that no longer exists', () => {
    useStore.setState({
      nodes: [makeNode('text-1')],
      edges: [
        { id: 'e1', source: 'a', target: 'text-1', targetHandle: 'text-1-gone' },
        { id: 'e2', source: 'a', target: 'text-1', targetHandle: 'text-1-kept' },
      ],
    });

    store().pruneNodeHandles('text-1', ['text-1-kept']);
    expect(store().edges.map((e) => e.id)).toEqual(['e2']);
  });

  test('leaves the graph alone when nothing is orphaned', () => {
    const edges = [
      { id: 'e1', source: 'a', target: 'text-1', targetHandle: 'text-1-kept' },
    ];
    useStore.setState({ nodes: [makeNode('text-1')], edges });

    store().pruneNodeHandles('text-1', ['text-1-kept']);
    expect(store().edges).toBe(edges); // Same reference: no needless re-render.
  });

  test('does not add a history entry of its own', () => {
    // Pruning is a consequence of the edit that already committed, so undo
    // has to reverse both together.
    useStore.setState({
      nodes: [makeNode('text-1')],
      edges: [{ id: 'e1', source: 'a', target: 'text-1', targetHandle: 'text-1-gone' }],
    });

    store().pruneNodeHandles('text-1', []);
    expect(store().past).toHaveLength(0);
  });
});

describe('selection actions', () => {
  test('delete removes the selected nodes and their edges', () => {
    useStore.setState({
      nodes: [{ ...makeNode('a'), selected: true }, makeNode('b')],
      edges: [{ id: 'e1', source: 'a', target: 'b' }],
    });

    store().deleteSelected();
    expect(store().nodes.map((n) => n.id)).toEqual(['b']);
    expect(store().edges).toHaveLength(0);
  });

  test('delete with nothing selected is a no-op', () => {
    useStore.setState({ nodes: [makeNode('a')] });
    store().deleteSelected();
    expect(store().nodes).toHaveLength(1);
    expect(store().past).toHaveLength(0);
  });

  test('duplicate copies the selection with fresh ids', () => {
    useStore.setState({
      nodes: [{ ...makeNode('text-1', 'text', { text: 'hello' }), selected: true }],
      nodeIDs: { text: 1 },
    });

    store().duplicateSelected();
    const copy = store().nodes[1];

    expect(store().nodes).toHaveLength(2);
    expect(copy.id).toBe('text-2');
    expect(copy.data.text).toBe('hello');
    expect(copy.data.id).toBe('text-2');
  });

  test('a duplicate is offset so it does not hide the original', () => {
    useStore.setState({
      nodes: [{ ...makeNode('text-1'), position: { x: 10, y: 10 }, selected: true }],
      nodeIDs: { text: 1 },
    });

    store().duplicateSelected();
    expect(store().nodes[1].position).toEqual({ x: 50, y: 50 });
  });
});

describe('results', () => {
  test('editing the graph clears the last run', () => {
    // A report about a graph that no longer exists is worse than none.
    useStore.setState({ run: { status: 'ok', steps: [] }, issues: [{ code: 'X' }] });
    store().addNode(makeNode('a'));

    expect(store().run).toBeNull();
    expect(store().issues).toEqual([]);
  });

  test('stats carry their issues across', () => {
    store().setStats({ num_nodes: 1, issues: [{ code: 'ISOLATED_NODE' }] });
    expect(store().issues).toHaveLength(1);
  });
});

describe('persistence', () => {
  test('a saved pipeline comes back', () => {
    store().addNode(makeNode('text-1', 'text', { text: 'remember me' }));
    store().setPipelineName('Memo');
    expect(store().saveToBrowser()).toBe(true);

    useStore.setState({ nodes: [], edges: [] });
    expect(store().restoreFromBrowser()).toBe(true);
    expect(store().nodes[0].data.text).toBe('remember me');
    expect(store().pipelineName).toBe('Memo');
  });

  test('restoring with nothing saved reports false', () => {
    expect(store().restoreFromBrowser()).toBe(false);
  });

  test('clear empties the canvas and the saved copy', () => {
    store().addNode(makeNode('text-1'));
    store().saveToBrowser();
    store().clear();

    expect(store().nodes).toEqual([]);
    expect(store().restoreFromBrowser()).toBe(false);
  });

  test('clear is undoable', () => {
    store().addNode(makeNode('text-1'));
    store().clear();
    store().undo();
    expect(store().nodes).toHaveLength(1);
  });
});

describe('auto-layout action', () => {
  test('repositions an acyclic pipeline and reports success', () => {
    useStore.setState({
      nodes: [makeNode('a'), makeNode('b')],
      edges: [{ id: 'e1', source: 'a', target: 'b' }],
    });

    expect(store().applyAutoLayout()).toBe(true);
    expect(store().nodes[1].position.x).toBeGreaterThan(store().nodes[0].position.x);
  });

  test('refuses a cyclic pipeline and changes nothing', () => {
    useStore.setState({
      nodes: [makeNode('a'), makeNode('b')],
      edges: [
        { id: 'e1', source: 'a', target: 'b' },
        { id: 'e2', source: 'b', target: 'a' },
      ],
    });

    expect(store().applyAutoLayout()).toBe(false);
    expect(store().nodes[0].position).toEqual({ x: 0, y: 0 });
  });
});

describe('severityFor', () => {
  test('an error outranks a warning', () => {
    expect(severityFor([{ severity: 'warning' }, { severity: 'error' }])).toBe('error');
  });

  test('warnings are reported when there is no error', () => {
    expect(severityFor([{ severity: 'warning' }])).toBe('warning');
  });

  test('info alone does not mark a node', () => {
    expect(severityFor([{ severity: 'info' }])).toBeNull();
  });

  test('an empty list is unmarked', () => {
    expect(severityFor([])).toBeNull();
  });
});
