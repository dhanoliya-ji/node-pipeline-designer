// nodeConfigs.js
// Every node in the pipeline, described as data.
//
// A config supports:
//   type        unique key, also the React Flow node type
//   label       title shown in the header and the toolbar
//   icon        glyph shown in the header
//   accent      token name from index.css (--accent-*)
//   description one-line subtitle
//   width       px number, or 'auto' to size to content
//   fields      array — or ({ id, data }) => array — of field specs
//   handles     array — or ({ id, data }) => array — of handle specs
//
// Field spec:  { name, label, type, default, placeholder, options, hint, ... }
//              type: text | textarea | select | number | checkbox | slider | readonly
//              `default` may be a value or ({ id, data }) => value
// Handle spec: { name, type: 'source' | 'target', position, label }
//              a handle's DOM id is `${nodeId}-${name}`
//
// Adding a node = adding one object here. No new files, no JSX, no styling.
// --------------------------------------------------

import { extractVariables } from './textVariables';

// Derives "input_1" from the node id "customInput-1".
const nameFromId = (prefix) => ({ id }) => id.replace(/^[^-]+-/, `${prefix}_`);

export const nodeConfigs = [
  // ---- The four original nodes, rebuilt as config ----
  {
    type: 'customInput',
    label: 'Input',
    icon: '▸',
    accent: 'green',
    description: 'Pipeline entry point',
    fields: [
      { name: 'inputName', label: 'Name', type: 'text', default: nameFromId('input') },
      {
        name: 'inputType',
        label: 'Type',
        type: 'select',
        default: 'Text',
        options: ['Text', 'Number'],
      },
      // The value a run starts from. Without it an Input node is a label on
      // an empty socket; with it the pipeline has something to carry.
      {
        name: 'inputValue',
        label: 'Value',
        type: 'textarea',
        default: '',
        minRows: 1,
        maxRows: 4,
        placeholder: 'The value this input feeds into the pipeline…',
      },
    ],
    handles: [{ name: 'value', type: 'source', position: 'right' }],
  },

  {
    type: 'customOutput',
    label: 'Output',
    icon: '◼',
    accent: 'rose',
    description: 'Pipeline result',
    fields: [
      { name: 'outputName', label: 'Name', type: 'text', default: nameFromId('output') },
      { name: 'outputType', label: 'Type', type: 'select', default: 'Text', options: ['Text', 'Image'] },
    ],
    handles: [{ name: 'value', type: 'target', position: 'left' }],
  },

  {
    type: 'llm',
    label: 'LLM',
    icon: '✦',
    accent: 'violet',
    description: 'Large language model',
    fields: [
      {
        name: 'model',
        label: 'Model',
        type: 'select',
        default: 'gpt-4o',
        options: ['gpt-4o', 'llama-3.1-70b', 'mistral-large', 'gemini-1.5-pro'],
      },
      { name: 'temperature', label: 'Temperature', type: 'slider', default: 0.7, min: 0, max: 1, step: 0.1 },
    ],
    handles: [
      { name: 'system', type: 'target', position: 'left', label: 'system' },
      { name: 'prompt', type: 'target', position: 'left', label: 'prompt' },
      { name: 'response', type: 'source', position: 'right' },
    ],
  },

  {
    type: 'text',
    label: 'Text',
    icon: '¶',
    accent: 'blue',
    description: 'Template with {{variables}}',
    width: 'auto',
    fields: [
      {
        name: 'text',
        label: 'Text',
        type: 'textarea',
        default: '{{input}}',
        monospace: true,
        placeholder: 'Write text, use {{name}} to add an input…',
      },
    ],
    // Each {{variable}} in the text becomes a target handle on the left.
    handles: ({ data }) => [
      ...extractVariables(data?.text).map((variable) => ({
        name: variable,
        type: 'target',
        position: 'left',
        label: variable,
      })),
      { name: 'output', type: 'source', position: 'right' },
    ],
  },

  // ---- Five new nodes, each a single object ----
  {
    type: 'filter',
    label: 'Filter',
    icon: '⌇',
    accent: 'amber',
    description: 'Route by a condition',
    fields: [
      {
        name: 'operator',
        label: 'Condition',
        type: 'select',
        default: 'contains',
        options: [
          { value: 'contains', label: 'Contains' },
          { value: 'equals', label: 'Equals' },
          { value: 'startsWith', label: 'Starts with' },
          { value: 'matches', label: 'Matches regex' },
        ],
      },
      { name: 'operand', label: 'Value', type: 'text', default: '', placeholder: 'e.g. urgent' },
      { name: 'caseSensitive', type: 'checkbox', default: false, checkboxLabel: 'Case sensitive' },
    ],
    handles: [
      { name: 'input', type: 'target', position: 'left' },
      { name: 'pass', type: 'source', position: 'right', label: 'pass' },
      { name: 'fail', type: 'source', position: 'right', label: 'fail' },
    ],
  },

  {
    type: 'math',
    label: 'Math',
    icon: '∑',
    accent: 'cyan',
    description: 'Combine two numbers',
    fields: [
      {
        name: 'operation',
        label: 'Operation',
        type: 'select',
        default: 'add',
        options: [
          { value: 'add', label: 'Add (a + b)' },
          { value: 'subtract', label: 'Subtract (a − b)' },
          { value: 'multiply', label: 'Multiply (a × b)' },
          { value: 'divide', label: 'Divide (a ÷ b)' },
        ],
      },
      { name: 'precision', label: 'Decimals', type: 'number', default: 2, min: 0, max: 10 },
    ],
    handles: [
      { name: 'a', type: 'target', position: 'left', label: 'a' },
      { name: 'b', type: 'target', position: 'left', label: 'b' },
      { name: 'result', type: 'source', position: 'right' },
    ],
  },

  {
    type: 'api',
    label: 'API Request',
    icon: '⇄',
    accent: 'orange',
    description: 'Call an HTTP endpoint',
    width: 260,
    fields: [
      {
        name: 'method',
        label: 'Method',
        type: 'select',
        default: 'GET',
        options: ['GET', 'POST', 'PUT', 'DELETE'],
      },
      { name: 'url', label: 'URL', type: 'text', default: '', placeholder: 'https://api.example.com/v1' },
      { name: 'timeout', label: 'Timeout (s)', type: 'number', default: 30, min: 1, max: 300 },
    ],
    handles: [
      { name: 'body', type: 'target', position: 'left', label: 'body' },
      { name: 'response', type: 'source', position: 'right', label: 'ok' },
      { name: 'error', type: 'source', position: 'right', label: 'err' },
    ],
  },

  {
    type: 'condition',
    label: 'Condition',
    icon: '⑂',
    accent: 'pink',
    description: 'Branch on an expression',
    fields: [
      {
        name: 'expression',
        label: 'Expression',
        type: 'textarea',
        default: 'value > 0',
        monospace: true,
        minRows: 2,
        maxRows: 6,
        hint: 'Evaluated against the incoming value.',
      },
    ],
    handles: [
      { name: 'value', type: 'target', position: 'left' },
      { name: 'true', type: 'source', position: 'right', label: 'true' },
      { name: 'false', type: 'source', position: 'right', label: 'false' },
    ],
  },

  {
    type: 'merge',
    label: 'Merge',
    icon: '⇉',
    accent: 'teal',
    description: 'Join several inputs',
    fields: [
      {
        name: 'strategy',
        label: 'Strategy',
        type: 'select',
        default: 'concat',
        options: [
          { value: 'concat', label: 'Concatenate' },
          { value: 'array', label: 'Collect as array' },
          { value: 'object', label: 'Merge as object' },
        ],
      },
      { name: 'separator', label: 'Separator', type: 'text', default: '\\n', placeholder: '\\n' },
      { name: 'inputCount', label: 'Inputs', type: 'number', default: 2, min: 2, max: 6 },
    ],
    // The number of input handles follows the "Inputs" field above.
    handles: ({ data }) => {
      const count = Math.min(6, Math.max(2, Number(data?.inputCount) || 2));
      return [
        ...Array.from({ length: count }, (_, i) => ({
          name: `input_${i + 1}`,
          type: 'target',
          position: 'left',
          label: `${i + 1}`,
        })),
        { name: 'merged', type: 'source', position: 'right' },
      ];
    },
  },
];
