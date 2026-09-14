// App.js
// The application shell: header, palette, canvas, results drawer.
// --------------------------------------------------

import { useCallback, useEffect, useState } from 'react';
import { ReactFlowProvider } from 'reactflow';

import { Canvas } from './components/Canvas';
import { InspectorPanel } from './components/InspectorPanel';
import { NodePalette } from './components/NodePalette';
import { TopBar } from './components/TopBar';
import { useStore } from './store';
import './App.css';

// How long the canvas stays quiet after an edit before the pipeline is
// written to localStorage. Long enough that typing does not cause a write
// per keystroke, short enough that a reload rarely loses anything.
const AUTOSAVE_DELAY = 1200;

function App() {
  const [panelOpen, setPanelOpen] = useState(false);
  const nodes = useStore((state) => state.nodes);
  const edges = useStore((state) => state.edges);
  const pipelineName = useStore((state) => state.pipelineName);

  // Restore whatever was on the canvas last time, once, before the first
  // autosave has a chance to overwrite it with an empty graph.
  const [restored, setRestored] = useState(false);
  useEffect(() => {
    useStore.getState().restoreFromBrowser();
    setRestored(true);
  }, []);

  useEffect(() => {
    if (!restored) return undefined;
    const timer = window.setTimeout(
      () => useStore.getState().saveToBrowser(),
      AUTOSAVE_DELAY
    );
    return () => window.clearTimeout(timer);
  }, [restored, nodes, edges, pipelineName]);

  // Any backend result is worth showing immediately; the user asked for it.
  const revealResults = useCallback(() => setPanelOpen(true), []);

  return (
    <ReactFlowProvider>
      <div className="app">
        <TopBar onResults={revealResults} />

        <div className="app__body">
          <NodePalette />
          <div className="app__workspace">
            <Canvas />
            <InspectorPanel open={panelOpen} onToggle={setPanelOpen} />
          </div>
        </div>
      </div>
    </ReactFlowProvider>
  );
}

export default App;
