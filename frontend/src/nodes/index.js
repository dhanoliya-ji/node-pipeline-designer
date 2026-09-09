// nodes/index.js
// Turns the node configs into everything the app needs: the React Flow
// nodeTypes map, the toolbar list, and each node's starting data.
// Nothing else in the app enumerates node types by hand.
// --------------------------------------------------

import { BaseNode } from '../components/BaseNode';
import { nodeConfigs } from './nodeConfigs';

const resolve = (value, ctx) => (typeof value === 'function' ? value(ctx) : value);

const createNodeType = (config) => {
  const NodeType = (props) => <BaseNode {...props} config={config} />;
  NodeType.displayName = `${config.label.replace(/\s/g, '')}Node`;
  return NodeType;
};

export const nodeTypes = Object.fromEntries(
  nodeConfigs.map((config) => [config.type, createNodeType(config)])
);

export const configByType = Object.fromEntries(
  nodeConfigs.map((config) => [config.type, config])
);

// Seeds a new node's data with every field default so the store is the
// single source of truth from the moment the node lands on the canvas.
export const getInitialNodeData = (id, type) => {
  const config = configByType[type];
  const data = { id, nodeType: type };
  if (!config) return data;

  const fields = resolve(config.fields, { id, data }) || [];
  fields.forEach((field) => {
    const value = resolve(field.default, { id, data });
    if (value !== undefined) {
      data[field.name] = value;
    }
  });

  return data;
};

export { nodeConfigs };
