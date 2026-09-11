// NodePalette.js
// The node palette, driven entirely by the config registry — a new entry in
// nodes/nodeConfigs.js appears here without this file changing.
// --------------------------------------------------

import { useMemo, useState } from 'react';
import { nodeConfigs } from '../nodes';
import { DraggableNode } from './DraggableNode';

export const NodePalette = () => {
  const [query, setQuery] = useState('');

  const matches = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return nodeConfigs;
    return nodeConfigs.filter((config) =>
      `${config.label} ${config.description || ''} ${config.type}`
        .toLowerCase()
        .includes(needle)
    );
  }, [query]);

  return (
    <aside className="palette">
      <div className="palette__heading">
        <h2 className="palette__title">Nodes</h2>
        <p className="palette__hint">Drag onto the canvas to build a pipeline.</p>
      </div>

      <input
        className="palette__search"
        type="search"
        value={query}
        placeholder="Search nodes…"
        onChange={(event) => setQuery(event.target.value)}
        aria-label="Search nodes"
      />

      <div className="palette__grid">
        {matches.map((config) => (
          <DraggableNode key={config.type} config={config} />
        ))}
      </div>

      {matches.length === 0 && (
        <p className="palette__empty">No node matches “{query}”.</p>
      )}
    </aside>
  );
};
