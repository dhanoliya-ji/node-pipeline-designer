// textVariables.js
// Pulls {{ variable }} references out of a template string.
// Only valid, non-reserved JavaScript identifiers count as variables, so
// prose like "{{ 2 + 2 }}" or "{{ my var }}" never produces a handle.
// --------------------------------------------------

const TEMPLATE_TOKEN = /\{\{([^{}]*)\}\}/g;
const IDENTIFIER = /^[A-Za-z_$][A-Za-z0-9_$]*$/;

const RESERVED = new Set([
  'break', 'case', 'catch', 'class', 'const', 'continue', 'debugger',
  'default', 'delete', 'do', 'else', 'enum', 'export', 'extends', 'false',
  'finally', 'for', 'function', 'if', 'import', 'in', 'instanceof', 'new',
  'null', 'return', 'super', 'switch', 'this', 'throw', 'true', 'try',
  'typeof', 'var', 'void', 'while', 'with', 'yield', 'let', 'static',
  'implements', 'interface', 'package', 'private', 'protected', 'public',
  'await',
]);

export const isValidVariableName = (name) =>
  IDENTIFIER.test(name) && !RESERVED.has(name);

// Returns unique variable names in the order they first appear.
export const extractVariables = (text) => {
  const found = [];
  const matches = String(text ?? '').matchAll(TEMPLATE_TOKEN);

  for (const match of matches) {
    const name = match[1].trim();
    if (isValidVariableName(name) && !found.includes(name)) {
      found.push(name);
    }
  }

  return found;
};
