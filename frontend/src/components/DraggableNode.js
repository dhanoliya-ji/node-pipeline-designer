// draggableNode.js
// A palette entry. Renders straight from a node config, so the toolbar
// stays in sync with nodes/nodeConfigs.js automatically.
// --------------------------------------------------

export const DraggableNode = ({ config }) => {
  const onDragStart = (event) => {
    event.target.style.cursor = 'grabbing';
    event.dataTransfer.setData(
      'application/reactflow',
      JSON.stringify({ nodeType: config.type })
    );
    event.dataTransfer.effectAllowed = 'move';
  };

  return (
    <div
      className="palette-item"
      style={{ '--node-accent': `var(--accent-${config.accent || 'blue'})` }}
      onDragStart={onDragStart}
      onDragEnd={(event) => (event.target.style.cursor = 'grab')}
      title={config.description}
      draggable
    >
      <span className="palette-item__icon" aria-hidden="true">
        {config.icon}
      </span>
      <span className="palette-item__label">{config.label}</span>
    </div>
  );
};
