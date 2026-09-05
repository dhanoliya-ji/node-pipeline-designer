// lib/layout.js
// Automatic canvas layout.
//
// A pipeline's topological levels are exactly its columns: every node sits
// one column to the right of its deepest predecessor, so no edge ever points
// backwards and the drawing reads left to right. Within a column, nodes are
// ordered by the average position of their parents, which keeps crossing
// edges to a minimum without a full Sugiyama pass.
// --------------------------------------------------

import { topologicalSort } from './graph';

const COLUMN_WIDTH = 320;
const ROW_HEIGHT = 190;
const ORIGIN = { x: 80, y: 60 };

// Groups node ids by their level, preserving the topological order within
// each group so the result is deterministic for a given graph.
const columnsFrom = (order, levels) => {
  const columns = [];
  order.forEach((id) => {
    const level = levels.get(id) ?? 0;
    (columns[level] = columns[level] || []).push(id);
  });
  return columns;
};

// The mean row of a node's already-placed parents. Used to pull a node
// vertically towards whatever feeds it.
const parentAnchor = (id, parents, rows) => {
  const placed = (parents.get(id) || [])
    .map((parent) => rows.get(parent))
    .filter((row) => row !== undefined);

  if (!placed.length) return null;
  return placed.reduce((sum, row) => sum + row, 0) / placed.length;
};

/**
 * Returns a new node array with `position` recomputed for every node.
 *
 * A cyclic graph has no meaningful column order, so the nodes are returned
 * untouched and the caller is told nothing moved — the user gets to see and
 * fix the loop rather than watch the canvas rearrange itself into a shape
 * that cannot be right.
 */
export const autoLayout = (nodes, edges) => {
  if (!nodes.length) return { nodes, changed: false };

  const { order, levels, isDag } = topologicalSort(nodes, edges);
  if (!isDag) return { nodes, changed: false };

  const parents = new Map(nodes.map((node) => [node.id, []]));
  edges.forEach((edge) => {
    if (parents.has(edge.target)) parents.get(edge.target).push(edge.source);
  });

  const columns = columnsFrom(order, levels);
  const rows = new Map();

  columns.forEach((column) => {
    // Sort by where the parents ended up, falling back to the topological
    // order for roots, which have no parents to follow.
    const sorted = [...column].sort((a, b) => {
      const anchorA = parentAnchor(a, parents, rows);
      const anchorB = parentAnchor(b, parents, rows);
      if (anchorA === null && anchorB === null) return 0;
      if (anchorA === null) return -1;
      if (anchorB === null) return 1;
      return anchorA - anchorB;
    });

    sorted.forEach((id, row) => rows.set(id, row));
  });

  // Centre each column vertically against the tallest one, so the diagram
  // balances around a horizontal axis instead of hanging off the top.
  const tallest = Math.max(...columns.map((column) => column.length), 1);

  const positioned = nodes.map((node) => {
    const level = levels.get(node.id);
    if (level === undefined) return node;

    const column = columns[level] || [];
    const row = rows.get(node.id) ?? 0;
    const offset = (tallest - column.length) / 2;

    return {
      ...node,
      position: {
        x: ORIGIN.x + level * COLUMN_WIDTH,
        y: ORIGIN.y + (row + offset) * ROW_HEIGHT,
      },
    };
  });

  return { nodes: positioned, changed: true };
};

export const LAYOUT_METRICS = { COLUMN_WIDTH, ROW_HEIGHT, ORIGIN };
