// BaseNode.js
// The single component every node in the pipeline is built from.
//
// A node is described by a plain config object (see nodes/nodeConfigs.js);
// BaseNode turns that description into chrome, fields, handles and state
// wiring. Node authors never touch layout, styling or the store.
//
// `fields` and `handles` may each be a static array or a function of
// { id, data } — the function form is what lets a node derive its handles
// from its own live state (the Text node's {{variables}} do exactly that).
// --------------------------------------------------

import { useEffect, useMemo } from 'react';
import { Handle, Position } from 'reactflow';
import { useStore, severityFor } from '../store';
import { NodeField } from './NodeField';
import './BaseNode.css';

const POSITIONS = {
  left: Position.Left,
  right: Position.Right,
  top: Position.Top,
  bottom: Position.Bottom,
};

const resolve = (value, ctx) => (typeof value === 'function' ? value(ctx) : value);

const handleKey = (nodeId, handle) => handle.id || `${nodeId}-${handle.name}`;

// Spreads handles evenly along their edge: two handles on a side sit at
// 33%/66%, three at 25%/50%/75%, and so on.
const offsetFor = (index, total) => `${((index + 1) / (total + 1)) * 100}%`;

// A run's output can be any JSON value, and it is being shown in a chip a
// couple of lines tall, so it is stringified and clipped.
const preview = (value) => {
  if (value === null || value === undefined) return '—';
  const text = typeof value === 'string' ? value : JSON.stringify(value);
  return text.length > 140 ? `${text.slice(0, 137)}…` : text;
};

export const BaseNode = ({ id, data, selected, config }) => {
  const updateNodeField = useStore((state) => state.updateNodeField);
  const pruneNodeHandles = useStore((state) => state.pruneNodeHandles);

  // The selectors return the stored arrays themselves, never a derived one:
  // React 18 compares snapshots by identity, and a selector that builds a
  // fresh array every call would re-render on each store read. The slice
  // belonging to this node is taken in a memo instead.
  const allIssues = useStore((state) => state.issues);
  const run = useStore((state) => state.run);

  const issues = useMemo(
    () => allIssues.filter((issue) => issue.node_id === id),
    [allIssues, id]
  );
  const step = useMemo(
    () => run?.steps?.find((entry) => entry.node_id === id) || null,
    [run, id]
  );

  const severity = severityFor(issues);

  const ctx = useMemo(() => ({ id, data }), [id, data]);
  const fields = useMemo(() => resolve(config.fields, ctx) || [], [config, ctx]);
  const handles = useMemo(() => resolve(config.handles, ctx) || [], [config, ctx]);

  const grouped = useMemo(() => {
    return handles.reduce((groups, handle) => {
      const side = handle.position || (handle.type === 'source' ? 'right' : 'left');
      (groups[side] = groups[side] || []).push(handle);
      return groups;
    }, {});
  }, [handles]);

  // When a data-driven handle disappears, any edge attached to it must go too.
  const handleIds = handles.map((handle) => handleKey(id, handle)).join('|');
  useEffect(() => {
    pruneNodeHandles(id, handleIds ? handleIds.split('|') : []);
  }, [id, handleIds, pruneNodeHandles]);

  const valueOf = (field) => {
    const current = data?.[field.name];
    if (current !== undefined) return current;
    const fallback = resolve(field.default, ctx);
    return fallback === undefined ? '' : fallback;
  };

  const classes = [
    'base-node',
    selected && 'base-node--selected',
    severity && `base-node--${severity}`,
    step && `base-node--run-${step.status}`,
  ]
    .filter(Boolean)
    .join(' ');

  return (
    <div
      className={classes}
      style={{
        '--node-accent': `var(--accent-${config.accent || 'blue'})`,
        width: config.width || 240,
      }}
    >
      <header className="base-node__header">
        <span className="base-node__icon" aria-hidden="true">
          {config.icon}
        </span>
        <div className="base-node__titles">
          <h3 className="base-node__title">{config.label}</h3>
          {config.description && (
            <p className="base-node__subtitle">{config.description}</p>
          )}
        </div>
        {severity && (
          <span
            className={`base-node__badge base-node__badge--${severity}`}
            title={issues.map((issue) => issue.message).join('\n')}
          >
            {severity === 'error' ? '!' : '?'}
          </span>
        )}
      </header>

      {fields.length > 0 && (
        <div className="base-node__body">
          {fields.map((field) => (
            <NodeField
              key={field.name}
              field={{ ...field, nodeId: id }}
              value={valueOf(field)}
              onChange={(value) => updateNodeField(id, field.name, value)}
            />
          ))}
        </div>
      )}

      {step && (
        <footer className={`base-node__result base-node__result--${step.status}`}>
          {step.status === 'ok' && (
            <span className="base-node__result-text">
              {preview(Object.values(step.outputs || {})[0])}
            </span>
          )}
          {step.status !== 'ok' && (
            <span className="base-node__result-text">
              {step.status === 'skipped' ? 'skipped' : step.message}
            </span>
          )}
        </footer>
      )}

      {config.footer && (
        <footer className="base-node__footer">{resolve(config.footer, ctx)}</footer>
      )}

      {Object.entries(grouped).map(([side, sideHandles]) =>
        sideHandles.map((handle, index) => {
          const key = handleKey(id, handle);
          const isVertical = side === 'left' || side === 'right';
          const offset = offsetFor(index, sideHandles.length);

          return (
            <Handle
              key={key}
              id={key}
              type={handle.type}
              position={POSITIONS[side]}
              className="base-node__handle"
              style={isVertical ? { top: offset } : { left: offset }}
            >
              {handle.label && (
                <span
                  className={`base-node__handle-label base-node__handle-label--${side}`}
                >
                  {handle.label}
                </span>
              )}
            </Handle>
          );
        })
      )}
    </div>
  );
};
