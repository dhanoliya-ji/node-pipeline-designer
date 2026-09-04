import {
  findIsolatedNodes,
  isDag,
  summarise,
  topologicalSort,
  wouldCreateCycle,
} from './graph';

// Terse builders so each test reads as the shape of graph it is about.
const n = (...ids) => ids.map((id) => ({ id }));
const e = (...pairs) =>
  pairs.map(([source, target]) => ({ id: `${source}->${target}`, source, target }));

describe('topologicalSort', () => {
  test('orders a chain from its root', () => {
    const { order } = topologicalSort(n('a', 'b', 'c'), e(['a', 'b'], ['b', 'c']));
    expect(order).toEqual(['a', 'b', 'c']);
  });

  test('places every node before its dependents', () => {
    const nodes = n('a', 'b', 'c', 'd');
    const edges = e(['a', 'b'], ['a', 'c'], ['b', 'd'], ['c', 'd']);
    const { order } = topologicalSort(nodes, edges);

    const at = Object.fromEntries(order.map((id, index) => [id, index]));
    edges.forEach(({ source, target }) => expect(at[source]).toBeLessThan(at[target]));
  });

  test('assigns a level one past the deepest parent', () => {
    // a -> b -> c and a -> c: c must sit at level 2, not level 1.
    const { levels } = topologicalSort(n('a', 'b', 'c'), e(['a', 'b'], ['b', 'c'], ['a', 'c']));
    expect(levels.get('a')).toBe(0);
    expect(levels.get('b')).toBe(1);
    expect(levels.get('c')).toBe(2);
  });

  test('gives parallel branches the same level', () => {
    const { levels } = topologicalSort(n('a', 'b', 'c'), e(['a', 'b'], ['a', 'c']));
    expect(levels.get('b')).toBe(levels.get('c'));
  });

  test('stops short on a cyclic graph', () => {
    const result = topologicalSort(n('a', 'b'), e(['a', 'b'], ['b', 'a']));
    expect(result.isDag).toBe(false);
    expect(result.order).toEqual([]);
  });

  test('ignores edges pointing at nodes that are not on the canvas', () => {
    const { order, isDag: acyclic } = topologicalSort(n('a'), e(['a', 'ghost']));
    expect(acyclic).toBe(true);
    expect(order).toEqual(['a']);
  });
});

describe('isDag', () => {
  test.each([
    ['an empty graph', [], []],
    ['a single node', n('a'), []],
    ['a chain', n('a', 'b'), e(['a', 'b'])],
    ['a diamond', n('a', 'b', 'c', 'd'), e(['a', 'b'], ['a', 'c'], ['b', 'd'], ['c', 'd'])],
    ['two components', n('a', 'b', 'c', 'd'), e(['a', 'b'], ['c', 'd'])],
  ])('accepts %s', (_label, nodes, edges) => {
    expect(isDag(nodes, edges)).toBe(true);
  });

  test.each([
    ['a self-loop', n('a'), e(['a', 'a'])],
    ['a two-node loop', n('a', 'b'), e(['a', 'b'], ['b', 'a'])],
    ['a three-node ring', n('a', 'b', 'c'), e(['a', 'b'], ['b', 'c'], ['c', 'a'])],
    ['a loop below a valid prefix', n('a', 'b', 'c'), e(['a', 'b'], ['b', 'c'], ['c', 'b'])],
  ])('rejects %s', (_label, nodes, edges) => {
    expect(isDag(nodes, edges)).toBe(false);
  });
});

describe('wouldCreateCycle', () => {
  // This is the check that runs while a connection is being dragged, so the
  // cases below are the ones a user can actually produce with the mouse.
  test('a node connected to itself is a cycle', () => {
    expect(wouldCreateCycle([], 'a', 'a')).toBe(true);
  });

  test('closing a loop back to an ancestor is a cycle', () => {
    expect(wouldCreateCycle(e(['a', 'b'], ['b', 'c']), 'c', 'a')).toBe(true);
  });

  test('an edge between unrelated nodes is fine', () => {
    expect(wouldCreateCycle(e(['a', 'b']), 'c', 'd')).toBe(false);
  });

  test('a second path forward is fine', () => {
    // a -> b -> c already exists; adding a -> c keeps it acyclic.
    expect(wouldCreateCycle(e(['a', 'b'], ['b', 'c']), 'a', 'c')).toBe(false);
  });

  test('a long chain is walked without a stack overflow', () => {
    const edges = Array.from({ length: 5000 }, (_, i) => ({
      id: `e${i}`,
      source: `n${i}`,
      target: `n${i + 1}`,
    }));
    expect(wouldCreateCycle(edges, 'n5000', 'n0')).toBe(true);
    expect(wouldCreateCycle(edges, 'n0', 'n5000')).toBe(false);
  });
});

describe('findIsolatedNodes', () => {
  test('lists nodes with no edges at all', () => {
    expect(findIsolatedNodes(n('a', 'b', 'c'), e(['a', 'b']))).toEqual(['c']);
  });

  test('a fully connected graph has none', () => {
    expect(findIsolatedNodes(n('a', 'b'), e(['a', 'b']))).toEqual([]);
  });
});

describe('summarise', () => {
  test('reports the counts and shape of a pipeline', () => {
    const summary = summarise(n('a', 'b', 'c'), e(['a', 'b']));
    expect(summary).toMatchObject({
      nodeCount: 3,
      edgeCount: 1,
      isDag: true,
      depth: 2,
      isolated: 1,
    });
  });

  test('withholds the depth of a cyclic pipeline', () => {
    expect(summarise(n('a', 'b'), e(['a', 'b'], ['b', 'a']))).toMatchObject({
      isDag: false,
      depth: 0,
    });
  });

  test('an empty canvas summarises to zeroes', () => {
    expect(summarise([], [])).toMatchObject({ nodeCount: 0, depth: 0, isDag: true });
  });
});
