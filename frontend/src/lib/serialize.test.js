import {
  FILE_VERSION,
  InvalidDocumentError,
  deriveNodeIds,
  fromDocument,
  toApiPayload,
  toDocument,
} from './serialize';

// A node as React Flow actually holds it: modelled fields plus a pile of
// view state the API has no business receiving.
const canvasNode = {
  id: 'text-1',
  type: 'text',
  position: { x: 10, y: 20 },
  data: { text: 'hi' },
  width: 240,
  height: 120,
  selected: true,
  dragging: false,
  positionAbsolute: { x: 10, y: 20 },
};

const canvasEdge = {
  id: 'e1',
  source: 'a',
  target: 'b',
  sourceHandle: 'a-value',
  targetHandle: 'b-value',
  type: 'smoothstep',
  animated: true,
  markerEnd: { type: 'arrowclosed' },
};

describe('toApiPayload', () => {
  test('sends only the fields the API models', () => {
    const payload = toApiPayload([canvasNode], [canvasEdge]);

    expect(Object.keys(payload.nodes[0]).sort()).toEqual(['data', 'id', 'type']);
    expect(Object.keys(payload.edges[0]).sort()).toEqual([
      'id',
      'source',
      'sourceHandle',
      'target',
      'targetHandle',
    ]);
  });

  test('does not leak positions or selection', () => {
    const json = JSON.stringify(toApiPayload([canvasNode], [canvasEdge]));
    expect(json).not.toContain('position');
    expect(json).not.toContain('selected');
  });

  test('an empty canvas produces empty lists', () => {
    expect(toApiPayload([], [])).toEqual({ nodes: [], edges: [] });
  });
});

describe('toDocument', () => {
  test('keeps positions, because a saved file has to reopen as it was', () => {
    const doc = toDocument([canvasNode], [canvasEdge], { name: 'Greeter' });
    expect(doc.nodes[0].position).toEqual({ x: 10, y: 20 });
  });

  test('stamps the version, name and time', () => {
    const doc = toDocument([canvasNode], [], { name: 'Greeter' });
    expect(doc.version).toBe(FILE_VERSION);
    expect(doc.name).toBe('Greeter');
    expect(Date.parse(doc.savedAt)).not.toBeNaN();
  });

  test('falls back to a placeholder name', () => {
    expect(toDocument([], []).name).toBe('Untitled pipeline');
  });

  test('still drops the renderer-only fields', () => {
    const doc = toDocument([canvasNode], [canvasEdge]);
    expect(doc.nodes[0].selected).toBeUndefined();
    expect(doc.edges[0].animated).toBeUndefined();
  });
});

describe('fromDocument', () => {
  const valid = {
    version: 1,
    name: 'Greeter',
    nodes: [{ id: 'text-1', type: 'text', position: { x: 1, y: 2 }, data: { text: 'x' } }],
    edges: [],
  };

  test('round-trips a document written by toDocument', () => {
    const doc = toDocument([canvasNode], [canvasEdge], { name: 'Greeter' });
    const restored = fromDocument(JSON.stringify(doc));

    expect(restored.name).toBe('Greeter');
    expect(restored.nodes[0].id).toBe('text-1');
    expect(restored.nodes[0].position).toEqual({ x: 10, y: 20 });
  });

  test('accepts an object as well as a JSON string', () => {
    expect(fromDocument(valid).nodes).toHaveLength(1);
  });

  test('supplies a position when one is missing', () => {
    const doc = { ...valid, nodes: [{ id: 'a', type: 'text' }] };
    expect(fromDocument(doc).nodes[0].position).toEqual({ x: 0, y: 0 });
  });

  test('drops edges whose endpoints are not present, and says how many', () => {
    const doc = {
      ...valid,
      edges: [
        { id: 'e1', source: 'text-1', target: 'ghost' },
        { id: 'e2', source: 'text-1', target: 'text-1' },
      ],
    };
    const restored = fromDocument(doc);

    expect(restored.edges).toHaveLength(1);
    expect(restored.droppedEdges).toBe(1);
  });

  test('rebuilds the id counters so new nodes do not collide', () => {
    const doc = {
      ...valid,
      nodes: [
        { id: 'text-1', type: 'text' },
        { id: 'text-7', type: 'text' },
        { id: 'llm-2', type: 'llm' },
      ],
    };
    expect(fromDocument(doc).nodeIDs).toEqual({ text: 7, llm: 2 });
  });

  test.each([
    ['not JSON at all', 'not json{'],
    ['a bare string', JSON.stringify('hello')],
    ['no node list', JSON.stringify({ edges: [] })],
    ['no edge list', JSON.stringify({ nodes: [] })],
    ['a node without an id', JSON.stringify({ nodes: [{ type: 'text' }], edges: [] })],
  ])('rejects %s with a readable message', (_label, raw) => {
    expect(() => fromDocument(raw)).toThrow(InvalidDocumentError);
  });

  test('refuses a file from a newer version of the app', () => {
    const doc = { ...valid, version: FILE_VERSION + 1 };
    expect(() => fromDocument(doc)).toThrow(/newer version/);
  });

  test('every rejection explains itself in plain language', () => {
    // The input is a file the user picked, so the failure has to be
    // something they can act on rather than a stack trace.
    try {
      fromDocument('not json{');
    } catch (error) {
      expect(error.message).toMatch(/valid JSON/);
    }
  });
});

describe('deriveNodeIds', () => {
  test('takes the highest counter seen per type', () => {
    expect(deriveNodeIds([{ id: 'text-3' }, { id: 'text-11' }, { id: 'text-2' }])).toEqual({
      text: 11,
    });
  });

  test('ignores ids that do not follow the pattern', () => {
    expect(deriveNodeIds([{ id: 'freeform' }, { id: 'llm-1' }])).toEqual({ llm: 1 });
  });

  test('handles a hyphenated type', () => {
    expect(deriveNodeIds([{ id: 'custom-input-4' }])).toEqual({ 'custom-input': 4 });
  });
});
