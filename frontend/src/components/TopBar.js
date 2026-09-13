// TopBar.js
// The application header: the pipeline's name, every action that operates on
// the whole pipeline, and a live indicator of whether the backend is up.
// --------------------------------------------------

import { useCallback, useEffect, useRef, useState } from 'react';
import {
  ApiError,
  executePipeline,
  fetchHealth,
  parsePipeline,
} from '../api/client';
import {
  InvalidDocumentError,
  downloadDocument,
  fromDocument,
  toDocument,
} from '../lib/serialize';
import { useStore } from '../store';
import { SHORTCUTS, useKeyboardShortcuts } from '../hooks/useKeyboardShortcuts';

const slugify = (name) =>
  (name || 'pipeline')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-|-$/g, '') || 'pipeline';

export const TopBar = ({ onResults }) => {
  const fileInput = useRef(null);
  const [health, setHealth] = useState('checking');
  const [toast, setToast] = useState(null);

  const nodes = useStore((state) => state.nodes);
  const edges = useStore((state) => state.edges);
  const pipelineName = useStore((state) => state.pipelineName);
  const isBusy = useStore((state) => state.isBusy);
  const past = useStore((state) => state.past);
  const future = useStore((state) => state.future);

  const {
    undo,
    redo,
    clear,
    setBusy,
    setStats,
    setRun,
    setApiError,
    setPipelineName,
    applyAutoLayout,
    deleteSelected,
    duplicateSelected,
    loadDocument,
    saveToBrowser,
  } = useStore.getState();

  // A toast is only ever transient feedback ("Saved", "Nothing to lay out"),
  // so it clears itself rather than needing to be dismissed.
  const flash = useCallback((message) => {
    setToast(message);
    window.setTimeout(() => setToast(null), 2600);
  }, []);

  useEffect(() => {
    let cancelled = false;
    fetchHealth()
      .then(() => !cancelled && setHealth('up'))
      .catch(() => !cancelled && setHealth('down'));
    return () => {
      cancelled = true;
    };
  }, []);

  const call = useCallback(
    async (operation, onSuccess) => {
      setBusy(true);
      try {
        const result = await operation();
        onSuccess(result);
        setHealth('up');
        onResults?.();
      } catch (error) {
        if (error instanceof ApiError) {
          setApiError(error.message);
          if (error.unreachable) setHealth('down');
          onResults?.();
        } else {
          throw error;
        }
      } finally {
        setBusy(false);
      }
    },
    [onResults, setApiError, setBusy]
  );

  const handleValidate = useCallback(
    () => call(() => parsePipeline(nodes, edges), setStats),
    [call, nodes, edges, setStats]
  );

  const handleRun = useCallback(
    () => call(() => executePipeline(nodes, edges), setRun),
    [call, nodes, edges, setRun]
  );

  const handleSave = useCallback(() => {
    flash(saveToBrowser() ? 'Saved to this browser.' : 'This browser blocked storage.');
  }, [flash, saveToBrowser]);

  const handleExport = useCallback(() => {
    downloadDocument(
      toDocument(nodes, edges, { name: pipelineName }),
      `${slugify(pipelineName)}.json`
    );
  }, [nodes, edges, pipelineName]);

  const handleImport = useCallback(
    async (event) => {
      const file = event.target.files?.[0];
      event.target.value = ''; // Allows re-importing the same file.
      if (!file) return;

      try {
        const document_ = fromDocument(await file.text());
        loadDocument(document_);
        flash(
          document_.droppedEdges
            ? `Imported. ${document_.droppedEdges} unusable edge(s) were dropped.`
            : `Imported ${document_.nodes.length} nodes.`
        );
      } catch (error) {
        flash(
          error instanceof InvalidDocumentError
            ? error.message
            : 'That file could not be read.'
        );
      }
    },
    [flash, loadDocument]
  );

  const handleLayout = useCallback(() => {
    if (!applyAutoLayout()) {
      flash(
        nodes.length
          ? 'A pipeline with a cycle cannot be laid out. Fix the loop first.'
          : 'There is nothing to lay out yet.'
      );
    }
  }, [applyAutoLayout, flash, nodes.length]);

  const handleClear = useCallback(() => {
    if (!nodes.length) return;
    // eslint-disable-next-line no-alert
    if (window.confirm('Remove every node and edge from the canvas?')) clear();
  }, [clear, nodes.length]);

  useKeyboardShortcuts({
    onUndo: undo,
    onRedo: redo,
    onSave: handleSave,
    onRun: handleRun,
    onLayout: handleLayout,
    onDelete: deleteSelected,
    onDuplicate: duplicateSelected,
  });

  const empty = nodes.length === 0;

  return (
    <header className="app__header">
      <div className="app__brand">
        <span className="app__logo" aria-hidden="true">
          ◆
        </span>
        <div>
          <h1 className="app__title">Node Pipeline Designer</h1>
          <input
            className="app__name"
            value={pipelineName}
            onChange={(event) => setPipelineName(event.target.value)}
            aria-label="Pipeline name"
            spellCheck="false"
          />
        </div>
      </div>

      <div className="app__actions">
        <div className="button-group">
          <button
            type="button"
            className="button button--ghost"
            onClick={undo}
            disabled={!past.length}
            title="Undo (Ctrl/Cmd + Z)"
          >
            ↶
          </button>
          <button
            type="button"
            className="button button--ghost"
            onClick={redo}
            disabled={!future.length}
            title="Redo (Ctrl/Cmd + Shift + Z)"
          >
            ↷
          </button>
        </div>

        <div className="button-group">
          <button
            type="button"
            className="button button--ghost"
            onClick={handleLayout}
            disabled={empty}
            title="Arrange the nodes by dependency order (Ctrl/Cmd + L)"
          >
            Auto-layout
          </button>
          <button
            type="button"
            className="button button--ghost"
            onClick={handleSave}
            title="Save to this browser (Ctrl/Cmd + S)"
          >
            Save
          </button>
          <button
            type="button"
            className="button button--ghost"
            onClick={handleExport}
            disabled={empty}
            title="Download this pipeline as JSON"
          >
            Export
          </button>
          <button
            type="button"
            className="button button--ghost"
            onClick={() => fileInput.current?.click()}
            title="Load a pipeline from a JSON file"
          >
            Import
          </button>
          <button
            type="button"
            className="button button--ghost button--danger"
            onClick={handleClear}
            disabled={empty}
            title="Remove everything from the canvas"
          >
            Clear
          </button>
        </div>

        <button
          type="button"
          className="button button--secondary"
          onClick={handleValidate}
          disabled={isBusy}
        >
          {isBusy ? 'Working…' : 'Validate'}
        </button>
        <button
          type="button"
          className="button button--primary"
          onClick={handleRun}
          disabled={isBusy || empty}
          title="Execute the pipeline (Ctrl/Cmd + Enter)"
        >
          {isBusy ? 'Working…' : 'Run'}
        </button>

        <span
          className={`health health--${health}`}
          title={
            health === 'up'
              ? 'The backend is responding.'
              : health === 'down'
              ? 'The backend is not reachable.'
              : 'Checking the backend…'
          }
        >
          <span className="health__dot" />
          {health === 'up' ? 'API' : health === 'down' ? 'API offline' : '…'}
        </span>
      </div>

      <input
        ref={fileInput}
        type="file"
        accept="application/json,.json"
        onChange={handleImport}
        hidden
      />

      {toast && <p className="toast">{toast}</p>}

      <details className="shortcuts">
        <summary className="shortcuts__summary" title="Keyboard shortcuts">
          ⌘
        </summary>
        <ul className="shortcuts__list">
          {SHORTCUTS.map((shortcut) => (
            <li key={shortcut.keys}>
              <kbd>{shortcut.keys}</kbd>
              <span>{shortcut.label}</span>
            </li>
          ))}
        </ul>
      </details>
    </header>
  );
};
