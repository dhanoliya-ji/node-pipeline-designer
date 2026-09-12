// InspectorPanel.js
// The results drawer: validation issues on one tab, the last run on the other.
//
// It is the only place the user reads what the backend said, so it has to be
// specific — every issue names the node it belongs to and clicking it selects
// that node on the canvas.
// --------------------------------------------------

import { useMemo, useState } from 'react';
import { useReactFlow } from 'reactflow';
import { useStore } from '../store';
import './InspectorPanel.css';

const SEVERITY_ICON = { error: '✕', warning: '!', info: 'i' };
const STATUS_ICON = { ok: '✓', skipped: '–', error: '✕' };

const formatValue = (value) => {
  if (value === null || value === undefined) return '—';
  if (typeof value === 'string') return value;
  return JSON.stringify(value, null, 2);
};

const formatMs = (ms) => (ms < 1 ? '<1 ms' : `${ms.toFixed(1)} ms`);

const IssueList = ({ issues, onSelect }) => {
  if (!issues.length) {
    return (
      <p className="inspector__empty">
        No issues found. The pipeline is a valid DAG and every node is wired
        correctly.
      </p>
    );
  }

  return (
    <ul className="inspector__list">
      {issues.map((issue, index) => (
        <li
          key={`${issue.code}-${issue.node_id || issue.edge_id || index}`}
          className={`issue issue--${issue.severity}${
            issue.node_id ? ' issue--selectable' : ''
          }`}
          onClick={() => issue.node_id && onSelect(issue.node_id)}
        >
          <span className={`issue__icon issue__icon--${issue.severity}`}>
            {SEVERITY_ICON[issue.severity]}
          </span>
          <div className="issue__body">
            <p className="issue__message">{issue.message}</p>
            <p className="issue__meta">
              <code>{issue.code}</code>
              {issue.node_id && <span> · {issue.node_id}</span>}
            </p>
          </div>
        </li>
      ))}
    </ul>
  );
};

const RunReport = ({ run, onSelect }) => {
  if (!run) {
    return (
      <p className="inspector__empty">
        Nothing has been run yet. Press <kbd>Run</kbd> to execute the pipeline
        and see what each node produced.
      </p>
    );
  }

  const outputs = Object.entries(run.outputs || {});

  return (
    <div className="run">
      <div className="run__summary">
        <span className={`run__status run__status--${run.status}`}>
          {run.status === 'ok' ? 'Completed' : 'Failed'}
        </span>
        <span className="run__timing">{formatMs(run.duration_ms)}</span>
        <span className="run__counts">
          {run.steps.filter((s) => s.status === 'ok').length} ran ·{' '}
          {run.steps.filter((s) => s.status === 'skipped').length} skipped ·{' '}
          {run.steps.filter((s) => s.status === 'error').length} failed
        </span>
      </div>

      {outputs.length > 0 && (
        <section className="run__outputs">
          <h4 className="run__heading">Pipeline output</h4>
          {outputs.map(([name, value]) => (
            <div className="run__output" key={name}>
              <span className="run__output-name">{name}</span>
              <pre className="run__output-value">{formatValue(value)}</pre>
            </div>
          ))}
        </section>
      )}

      <section>
        <h4 className="run__heading">Steps, in execution order</h4>
        <ol className="run__steps">
          {run.steps.map((step) => (
            <li
              key={step.node_id}
              className={`step step--${step.status}`}
              onClick={() => onSelect(step.node_id)}
            >
              <span className={`step__icon step__icon--${step.status}`}>
                {STATUS_ICON[step.status]}
              </span>
              <span className="step__id">{step.node_id}</span>
              <span className="step__detail">
                {step.status === 'ok'
                  ? formatValue(Object.values(step.outputs || {})[0])
                  : step.message}
              </span>
              <span className="step__timing">{formatMs(step.duration_ms)}</span>
            </li>
          ))}
        </ol>
      </section>
    </div>
  );
};

export const InspectorPanel = ({ open, onToggle }) => {
  const issues = useStore((state) => state.issues);
  const run = useStore((state) => state.run);
  const stats = useStore((state) => state.stats);
  const apiError = useStore((state) => state.apiError);
  const setNodes = useStore((state) => state.onNodesChange);
  const { fitView } = useReactFlow();

  const [tab, setTab] = useState('issues');

  const counts = useMemo(
    () => ({
      error: issues.filter((i) => i.severity === 'error').length,
      warning: issues.filter((i) => i.severity === 'warning').length,
    }),
    [issues]
  );

  // Selecting from the panel both highlights the node and brings it into
  // view, because the node being complained about is often off-screen.
  const selectNode = (nodeId) => {
    setNodes([{ id: nodeId, type: 'select', selected: true }]);
    fitView({ nodes: [{ id: nodeId }], duration: 400, maxZoom: 1.2, padding: 0.4 });
  };

  return (
    <section className={`inspector${open ? ' inspector--open' : ''}`}>
      <header className="inspector__bar">
        <div className="inspector__tabs">
          <button
            type="button"
            className={`inspector__tab${tab === 'issues' ? ' is-active' : ''}`}
            onClick={() => {
              setTab('issues');
              if (!open) onToggle(true);
            }}
          >
            Issues
            {counts.error > 0 && (
              <span className="inspector__count inspector__count--error">
                {counts.error}
              </span>
            )}
            {counts.error === 0 && counts.warning > 0 && (
              <span className="inspector__count inspector__count--warning">
                {counts.warning}
              </span>
            )}
          </button>
          <button
            type="button"
            className={`inspector__tab${tab === 'run' ? ' is-active' : ''}`}
            onClick={() => {
              setTab('run');
              if (!open) onToggle(true);
            }}
          >
            Run
            {run && (
              <span className={`inspector__count inspector__count--${run.status}`}>
                {run.steps.length}
              </span>
            )}
          </button>
        </div>

        {stats && (
          <p className="inspector__stats">
            {stats.num_nodes} nodes · {stats.num_edges} edges · depth{' '}
            {stats.depth} · {stats.is_dag ? 'acyclic' : 'cyclic'}
          </p>
        )}

        <button
          type="button"
          className="inspector__toggle"
          onClick={() => onToggle(!open)}
          aria-label={open ? 'Collapse panel' : 'Expand panel'}
        >
          {open ? '▾' : '▴'}
        </button>
      </header>

      {open && (
        <div className="inspector__content">
          {apiError && <p className="inspector__error">{apiError}</p>}
          {tab === 'issues' ? (
            <IssueList issues={issues} onSelect={selectNode} />
          ) : (
            <RunReport run={run} onSelect={selectNode} />
          )}
        </div>
      )}
    </section>
  );
};
