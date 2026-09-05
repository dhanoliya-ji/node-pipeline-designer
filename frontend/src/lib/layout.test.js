import { LAYOUT_METRICS, autoLayout } from './layout';

const { COLUMN_WIDTH, ORIGIN } = LAYOUT_METRICS;

const n = (...ids) => ids.map((id) => ({ id, position: { x: 0, y: 0 } }));
const e = (...pairs) =>
  pairs.map(([source, target]) => ({ id: `${source}->${target}`, source, target }));

const positionOf = (nodes, id) => nodes.find((node) => node.id === id).position;

describe('autoLayout', () => {
  test('places a chain in consecutive columns', () => {
    const { nodes, changed } = autoLayout(n('a', 'b', 'c'), e(['a', 'b'], ['b', 'c']));

    expect(changed).toBe(true);
    expect(positionOf(nodes, 'a').x).toBe(ORIGIN.x);
    expect(positionOf(nodes, 'b').x).toBe(ORIGIN.x + COLUMN_WIDTH);
    expect(positionOf(nodes, 'c').x).toBe(ORIGIN.x + COLUMN_WIDTH * 2);
  });

  test('every edge points rightwards', () => {
    const nodes = n('a', 'b', 'c', 'd');
    const edges = e(['a', 'b'], ['a', 'c'], ['b', 'd'], ['c', 'd']);
    const laid = autoLayout(nodes, edges).nodes;

    edges.forEach(({ source, target }) => {
      expect(positionOf(laid, source).x).toBeLessThan(positionOf(laid, target).x);
    });
  });

  test('parallel branches share a column but not a row', () => {
    const laid = autoLayout(n('a', 'b', 'c'), e(['a', 'b'], ['a', 'c'])).nodes;

    expect(positionOf(laid, 'b').x).toBe(positionOf(laid, 'c').x);
    expect(positionOf(laid, 'b').y).not.toBe(positionOf(laid, 'c').y);
  });

  test('a node waits for its deepest parent', () => {
    // a -> b -> c and a -> c: c belongs in column 2, past b.
    const laid = autoLayout(n('a', 'b', 'c'), e(['a', 'b'], ['b', 'c'], ['a', 'c'])).nodes;
    expect(positionOf(laid, 'c').x).toBe(ORIGIN.x + COLUMN_WIDTH * 2);
  });

  test('unconnected nodes all start in the first column', () => {
    const laid = autoLayout(n('a', 'b'), []).nodes;
    expect(positionOf(laid, 'a').x).toBe(ORIGIN.x);
    expect(positionOf(laid, 'b').x).toBe(ORIGIN.x);
  });

  test('no two nodes land on the same point', () => {
    const laid = autoLayout(n('a', 'b', 'c', 'd'), e(['a', 'c'], ['b', 'c'])).nodes;
    const points = laid.map(({ position }) => `${position.x},${position.y}`);
    expect(new Set(points).size).toBe(points.length);
  });

  test('a cyclic graph is left exactly as it was', () => {
    // There is no correct column order for a loop, and rearranging the canvas
    // would hide the very thing the user needs to see.
    const nodes = n('a', 'b');
    const { nodes: result, changed } = autoLayout(nodes, e(['a', 'b'], ['b', 'a']));

    expect(changed).toBe(false);
    expect(result).toBe(nodes);
  });

  test('an empty canvas reports nothing to do', () => {
    expect(autoLayout([], []).changed).toBe(false);
  });

  test('the input array is not mutated', () => {
    const nodes = n('a', 'b');
    autoLayout(nodes, e(['a', 'b']));
    expect(nodes[1].position).toEqual({ x: 0, y: 0 });
  });

  test('the same graph always lays out the same way', () => {
    const edges = e(['a', 'b'], ['a', 'c'], ['b', 'd']);
    const first = autoLayout(n('a', 'b', 'c', 'd'), edges).nodes;
    const second = autoLayout(n('a', 'b', 'c', 'd'), edges).nodes;
    expect(first.map((x) => x.position)).toEqual(second.map((x) => x.position));
  });
});
