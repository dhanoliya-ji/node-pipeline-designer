"""What each node type does when a pipeline runs.

Every handler is a plain function of (data, inputs) -> outputs, which keeps
them trivial to unit-test and keeps the engine free of any knowledge about
individual node types. Registering a new node is one `register(...)` call
here plus a matching config object on the frontend.

A handler may leave an output handle out of its return value. The engine
reads that as "nothing flowed down this path", which is how the branching
nodes (Filter, Condition) skip the branch that was not taken.
"""

import re
from typing import Any, Dict, List

from ..config import ALLOW_OUTBOUND_HTTP, HTTP_TIMEOUT_CEILING
from ..core.expressions import ExpressionError, evaluate_truthy
from .registry import NodeSpec, register

VARIABLE_PATTERN = re.compile(r'\{\{\s*([A-Za-z_$][A-Za-z0-9_$]*)\s*\}\}')


class NodeExecutionError(RuntimeError):
    """A node could not run. The engine turns this into a failed step."""


def extract_variables(text: Any) -> List[str]:
    """Pull the distinct {{variable}} names out of a template, in order.

    Mirrors `frontend/src/nodes/textVariables.js`; the two are covered by
    equivalent test cases so they cannot drift apart unnoticed.
    """
    if not isinstance(text, str):
        return []
    seen: List[str] = []
    for match in VARIABLE_PATTERN.finditer(text):
        name = match.group(1)
        if name not in seen:
            seen.append(name)
    return seen


def _as_number(value: Any, label: str) -> float:
    """Coerce an input to a number, or fail with a message a user can act on."""
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        raise NodeExecutionError("input '{}' is not a number: {!r}".format(label, value))


def _as_text(value: Any) -> str:
    if value is None:
        return ''
    if isinstance(value, bool):
        return 'true' if value else 'false'
    return value if isinstance(value, str) else str(value)


# --------------------------------------------------------------------------
# Input / Output
# --------------------------------------------------------------------------

def run_input(data: Dict[str, Any], inputs: Dict[str, Any]) -> Dict[str, Any]:
    """Emit the value the user typed into the node, coerced to its type."""
    value = data.get('inputValue', '')
    if data.get('inputType') == 'Number':
        value = _as_number(value, data.get('inputName', 'input'))
    return {'value': value}


def run_output(data: Dict[str, Any], inputs: Dict[str, Any]) -> Dict[str, Any]:
    """Terminal node: pass the value through so the engine can collect it."""
    return {'value': inputs.get('value')}


# --------------------------------------------------------------------------
# Text
# --------------------------------------------------------------------------

def run_text(data: Dict[str, Any], inputs: Dict[str, Any]) -> Dict[str, Any]:
    """Substitute each {{variable}} with the value on the matching handle.

    A variable with nothing connected is left as the literal `{{name}}` so
    the gap is visible in the output rather than silently becoming ''.
    """
    template = _as_text(data.get('text', ''))

    def substitute(match: 're.Match[str]') -> str:
        name = match.group(1)
        if name in inputs and inputs[name] is not None:
            return _as_text(inputs[name])
        return match.group(0)

    return {'output': VARIABLE_PATTERN.sub(substitute, template)}


# --------------------------------------------------------------------------
# LLM
# --------------------------------------------------------------------------

def run_llm(data: Dict[str, Any], inputs: Dict[str, Any]) -> Dict[str, Any]:
    """Stand in for a model call.

    No provider is wired up: this project is about the graph, not about
    holding someone's API key. The node returns a deterministic, clearly
    labelled echo so a pipeline containing an LLM still runs end to end and
    the surrounding wiring can be tested. Swapping in a real client means
    replacing this function body and nothing else.
    """
    model = data.get('model', 'gpt-4o')
    temperature = data.get('temperature', 0.7)
    prompt = _as_text(inputs.get('prompt', ''))
    system = _as_text(inputs.get('system', ''))

    preamble = '[{}] '.format(model)
    if system:
        preamble += '(system: {}) '.format(system.strip())

    body = prompt.strip() or '(no prompt connected)'
    return {
        'response': '{}simulated response to: {}'.format(preamble, body),
        '_meta': {'simulated': True, 'model': model, 'temperature': temperature},
    }


# --------------------------------------------------------------------------
# Math
# --------------------------------------------------------------------------

def run_math(data: Dict[str, Any], inputs: Dict[str, Any]) -> Dict[str, Any]:
    a = _as_number(inputs.get('a', 0), 'a')
    b = _as_number(inputs.get('b', 0), 'b')
    operation = data.get('operation', 'add')

    if operation == 'add':
        result = a + b
    elif operation == 'subtract':
        result = a - b
    elif operation == 'multiply':
        result = a * b
    elif operation == 'divide':
        if b == 0:
            raise NodeExecutionError('division by zero')
        result = a / b
    else:
        raise NodeExecutionError("unknown operation '{}'".format(operation))

    try:
        precision = max(0, min(10, int(data.get('precision', 2))))
    except (TypeError, ValueError):
        precision = 2

    rounded = round(result, precision)
    # Report a whole number as an int so downstream text reads "4", not "4.0".
    return {'result': int(rounded) if precision == 0 else rounded}


# --------------------------------------------------------------------------
# Filter
# --------------------------------------------------------------------------

def run_filter(data: Dict[str, Any], inputs: Dict[str, Any]) -> Dict[str, Any]:
    """Send the value down `pass` or `fail`, never both."""
    value = _as_text(inputs.get('input'))
    operand = _as_text(data.get('operand', ''))
    operator_name = data.get('operator', 'contains')

    haystack, needle = value, operand
    if not data.get('caseSensitive'):
        haystack, needle = haystack.lower(), needle.lower()

    if operator_name == 'contains':
        matched = needle in haystack
    elif operator_name == 'equals':
        matched = haystack == needle
    elif operator_name == 'startsWith':
        matched = haystack.startswith(needle)
    elif operator_name == 'matches':
        flags = 0 if data.get('caseSensitive') else re.IGNORECASE
        try:
            matched = re.search(operand, value, flags) is not None
        except re.error as error:
            raise NodeExecutionError('invalid regular expression: {}'.format(error))
    else:
        raise NodeExecutionError("unknown condition '{}'".format(operator_name))

    # Only the taken branch appears, so the other branch's subtree is skipped.
    return {'pass': inputs.get('input')} if matched else {'fail': inputs.get('input')}


# --------------------------------------------------------------------------
# Condition
# --------------------------------------------------------------------------

def run_condition(data: Dict[str, Any], inputs: Dict[str, Any]) -> Dict[str, Any]:
    expression = data.get('expression', '')
    try:
        taken = evaluate_truthy(expression, {'value': inputs.get('value')})
    except ExpressionError as error:
        raise NodeExecutionError('cannot evaluate expression: {}'.format(error))

    return {'true': inputs.get('value')} if taken else {'false': inputs.get('value')}


# --------------------------------------------------------------------------
# Merge
# --------------------------------------------------------------------------

def _merge_input_handles(data: Dict[str, Any]) -> List[str]:
    try:
        count = int(data.get('inputCount', 2))
    except (TypeError, ValueError):
        count = 2
    count = max(2, min(6, count))
    return ['input_{}'.format(i + 1) for i in range(count)]


def run_merge(data: Dict[str, Any], inputs: Dict[str, Any]) -> Dict[str, Any]:
    """Combine the connected inputs, in handle order, skipping the empty ones."""
    handles = _merge_input_handles(data)
    values = [inputs[h] for h in handles if h in inputs and inputs[h] is not None]
    strategy = data.get('strategy', 'concat')

    if strategy == 'array':
        return {'merged': values}
    if strategy == 'object':
        return {
            'merged': {
                h: inputs[h] for h in handles if h in inputs and inputs[h] is not None
            }
        }
    if strategy == 'concat':
        # '\n' typed into a text field arrives as a literal backslash-n.
        separator = _as_text(data.get('separator', '\n')).replace('\\n', '\n').replace('\\t', '\t')
        return {'merged': separator.join(_as_text(v) for v in values)}

    raise NodeExecutionError("unknown merge strategy '{}'".format(strategy))


# --------------------------------------------------------------------------
# API request
# --------------------------------------------------------------------------

def run_api(data: Dict[str, Any], inputs: Dict[str, Any]) -> Dict[str, Any]:
    """Call an HTTP endpoint, if the deployment allows outbound requests.

    Outbound HTTP is off unless NPD_ALLOW_OUTBOUND_HTTP=true, because a
    public demo that fetches any URL a visitor types is a request-forgery
    hole. With it off the node reports the call it would have made on its
    `error` handle, which keeps the branch wiring honest.
    """
    url = _as_text(data.get('url', '')).strip()
    method = _as_text(data.get('method', 'GET')).upper()

    if not url:
        return {'error': 'no URL configured'}

    if not ALLOW_OUTBOUND_HTTP:
        return {
            'error': 'outbound HTTP is disabled; set NPD_ALLOW_OUTBOUND_HTTP=true '
                     'to let this node call {} {}'.format(method, url)
        }

    if not url.startswith(('http://', 'https://')):
        return {'error': 'unsupported URL scheme: {}'.format(url)}

    try:
        timeout = min(HTTP_TIMEOUT_CEILING, float(data.get('timeout', 30) or 30))
    except (TypeError, ValueError):
        timeout = HTTP_TIMEOUT_CEILING

    try:
        import httpx
    except ImportError:
        return {'error': 'httpx is not installed; add it to run API nodes'}

    body = inputs.get('body')
    try:
        with httpx.Client(timeout=timeout, follow_redirects=False) as client:
            response = client.request(
                method,
                url,
                json=body if body is not None and method in ('POST', 'PUT') else None,
            )
    except Exception as error:  # httpx raises a family of transport errors.
        return {'error': '{}: {}'.format(type(error).__name__, error)}

    if response.status_code >= 400:
        return {'error': 'HTTP {}'.format(response.status_code)}

    try:
        return {'response': response.json()}
    except ValueError:
        return {'response': response.text}


# --------------------------------------------------------------------------
# Registration
# --------------------------------------------------------------------------

register(NodeSpec(
    type='customInput',
    label='Input',
    description='Pipeline entry point. Emits the value configured on the node.',
    outputs=('value',),
    handler=run_input,
))

register(NodeSpec(
    type='customOutput',
    label='Output',
    description='Pipeline result. Whatever reaches it is collected into the run output.',
    inputs=('value',),
    required_inputs=('value',),
    handler=run_output,
))

register(NodeSpec(
    type='text',
    label='Text',
    description='Template string. Each {{variable}} becomes an input handle.',
    outputs=('output',),
    dynamic_inputs=lambda data: extract_variables(data.get('text')),
    handler=run_text,
))

register(NodeSpec(
    type='llm',
    label='LLM',
    description='Large language model call (simulated in this build).',
    inputs=('system', 'prompt'),
    outputs=('response',),
    required_inputs=('prompt',),
    handler=run_llm,
))

register(NodeSpec(
    type='math',
    label='Math',
    description='Arithmetic on two numeric inputs.',
    inputs=('a', 'b'),
    outputs=('result',),
    required_inputs=('a', 'b'),
    handler=run_math,
))

register(NodeSpec(
    type='filter',
    label='Filter',
    description='Route a value to pass or fail by testing it against a condition.',
    inputs=('input',),
    outputs=('pass', 'fail'),
    required_inputs=('input',),
    handler=run_filter,
))

register(NodeSpec(
    type='condition',
    label='Condition',
    description='Branch on a boolean expression evaluated against the input.',
    inputs=('value',),
    outputs=('true', 'false'),
    required_inputs=('value',),
    handler=run_condition,
))

register(NodeSpec(
    type='merge',
    label='Merge',
    description='Join several inputs into one value.',
    outputs=('merged',),
    dynamic_inputs=_merge_input_handles,
    handler=run_merge,
))

register(NodeSpec(
    type='api',
    label='API Request',
    description='Call an HTTP endpoint and branch on success or failure.',
    inputs=('body',),
    outputs=('response', 'error'),
    handler=run_api,
))
