// Canvas.js
// The drag-and-drop pipeline canvas.
// --------------------------------------------------

import { useState, useRef, useCallback, useMemo } from 'react';
import ReactFlow, {
  Controls,
  Background,
  MiniMap,
  BackgroundVariant,
} from 'reactflow';
import { shallow } from 'zustand/shallow';
import { useStore, severityFor } from '../store';
import { nodeTypes, getInitialNodeData, configByType } from '../nodes';

import 'reactflow/dist/style.css';

const gridSize = 20;
const proOptions = { hideAttribution: true };

const selector = (state) => ({
  nodes: state.nodes,
  edges: state.edges,
  getNodeID: state.getNodeID,
  addNode: state.addNode,
  onNodesChange: state.onNodesChange,
  onEdgesChange: state.onEdgesChange,
  onConnect: state.onConnect,
  isValidConnection: state.isValidConnection,
});

// Colours the minimap dots with each node's own accent.
const accentOf = (node) => {
  const accent = configByType[node.type]?.accent || 'blue';
  return getComputedStyle(document.documentElement)
    .getPropertyValue(`--accent-${accent}`)
    .trim();
};

export const Canvas = () => {
  const wrapper = useRef(null);
  const [instance, setInstance] = useState(null);
  const {
    nodes,
    edges,
    getNodeID,
    addNode,
    onNodesChange,
    onEdgesChange,
    onConnect,
    isValidConnection,
  } = useStore(selector, shallow);

  const issues = useStore((state) => state.issues);
  const run = useStore((state) => state.run);

  // Paints the edges that carried a value during the last run, and the ones
  // attached to a node the validator complained about. Done here rather than
  // in the store so the stored graph stays exactly what gets saved.
  const decoratedEdges = useMemo(() => {
    const erroring = new Set(
      issues
        .filter((issue) => issue.severity === 'error' && issue.node_id)
        .map((issue) => issue.node_id)
    );
    const ran = new Set(
      (run?.steps || [])
        .filter((step) => step.status === 'ok')
        .map((step) => step.node_id)
    );

    return edges.map((edge) => {
      const onErrorPath = erroring.has(edge.source) || erroring.has(edge.target);
      const carried = ran.has(edge.source) && ran.has(edge.target);

      if (!onErrorPath && !carried) return edge;
      return {
        ...edge,
        className: onErrorPath ? 'edge--error' : 'edge--active',
      };
    });
  }, [edges, issues, run]);

  const decoratedNodes = useMemo(() => {
    if (!issues.length) return nodes;
    const byNode = {};
    issues.forEach((issue) => {
      if (!issue.node_id) return;
      (byNode[issue.node_id] = byNode[issue.node_id] || []).push(issue);
    });

    return nodes.map((node) =>
      byNode[node.id]
        ? { ...node, className: `node--${severityFor(byNode[node.id])}` }
        : node
    );
  }, [nodes, issues]);

  const onDrop = useCallback(
    (event) => {
      event.preventDefault();

      const payload = event?.dataTransfer?.getData('application/reactflow');
      if (!payload || !instance) return;

      let type;
      try {
        type = JSON.parse(payload)?.nodeType;
      } catch (error) {
        return; // Something else was dropped onto the canvas.
      }
      if (!type || !configByType[type]) return;

      const bounds = wrapper.current.getBoundingClientRect();
      const position = instance.project({
        x: event.clientX - bounds.left,
        y: event.clientY - bounds.top,
      });

      const nodeID = getNodeID(type);
      addNode({
        id: nodeID,
        type,
        position,
        data: getInitialNodeData(nodeID, type),
      });
    },
    [instance, getNodeID, addNode]
  );

  const onDragOver = useCallback((event) => {
    event.preventDefault();
    event.dataTransfer.dropEffect = 'move';
  }, []);

  return (
    <div className="canvas" ref={wrapper}>
      <ReactFlow
        nodes={decoratedNodes}
        edges={decoratedEdges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onConnect={onConnect}
        isValidConnection={isValidConnection}
        onDrop={onDrop}
        onDragOver={onDragOver}
        onInit={setInstance}
        nodeTypes={nodeTypes}
        proOptions={proOptions}
        snapGrid={[gridSize, gridSize]}
        connectionLineType="smoothstep"
        defaultEdgeOptions={{ type: 'smoothstep' }}
        deleteKeyCode={['Backspace', 'Delete']}
        fitView
      >
        <Background variant={BackgroundVariant.Dots} gap={gridSize} size={1.4} />
        <Controls showInteractive={false} />
        <MiniMap pannable zoomable nodeColor={accentOf} nodeStrokeWidth={0} />
      </ReactFlow>

      {nodes.length === 0 && (
        <div className="canvas__empty">
          <p className="canvas__empty-title">Your canvas is empty</p>
          <p className="canvas__empty-text">
            Drag a node from the left to get started, or import a saved
            pipeline.
          </p>
        </div>
      )}
    </div>
  );
};
