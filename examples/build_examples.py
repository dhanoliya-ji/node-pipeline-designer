"""Builds the example pipelines and checks each one actually runs.

The examples are generated rather than hand-written so they cannot drift out
of step with the node definitions, and so every one is proven to execute
before it is committed.

    backend/.venv/Scripts/python examples/build_examples.py
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))

from app.core.engine import execute  # noqa: E402
from app.core.validation import has_errors, validate  # noqa: E402
from app.schemas import Edge, Node  # noqa: E402

HERE = Path(__file__).resolve().parent


def node(node_id, node_type, position, **data):
    return {
        'id': node_id,
        'type': node_type,
        'position': {'x': position[0], 'y': position[1]},
        'data': {'id': node_id, **data},
    }


def edge(source, target, source_handle, target_handle):
    return {
        'id': '{}->{}'.format(source, target),
        'source': source,
        'target': target,
        'sourceHandle': '{}-{}'.format(source, source_handle),
        'targetHandle': '{}-{}'.format(target, target_handle),
    }


def document(name, nodes, edges):
    return {'version': 1, 'name': name, 'nodes': nodes, 'edges': edges}


# --------------------------------------------------------------------------
# 1. The smallest useful pipeline
# --------------------------------------------------------------------------

GREETING = document(
    'Greeting',
    [
        node('customInput-1', 'customInput', (80, 160),
             inputName='name', inputType='Text', inputValue='Ada'),
        node('text-1', 'text', (400, 150), text='Hello, {{name}}!'),
        node('customOutput-1', 'customOutput', (720, 160),
             outputName='greeting', outputType='Text'),
    ],
    [
        edge('customInput-1', 'text-1', 'value', 'name'),
        edge('text-1', 'customOutput-1', 'output', 'value'),
    ],
)


# --------------------------------------------------------------------------
# 2. Branching: one input, two possible outputs, only one taken
# --------------------------------------------------------------------------

TRIAGE = document(
    'Ticket triage',
    [
        node('customInput-1', 'customInput', (80, 200),
             inputName='ticket', inputType='Text',
             inputValue='URGENT: the checkout page is down'),
        node('filter-1', 'filter', (400, 190),
             operator='contains', operand='urgent', caseSensitive=False),
        node('text-1', 'text', (720, 80), text='ESCALATE: {{body}}'),
        node('text-2', 'text', (720, 320), text='queue normally: {{body}}'),
        node('customOutput-1', 'customOutput', (1040, 90), outputName='escalated'),
        node('customOutput-2', 'customOutput', (1040, 330), outputName='queued'),
    ],
    [
        edge('customInput-1', 'filter-1', 'value', 'input'),
        edge('filter-1', 'text-1', 'pass', 'body'),
        edge('filter-1', 'text-2', 'fail', 'body'),
        edge('text-1', 'customOutput-1', 'output', 'value'),
        edge('text-2', 'customOutput-2', 'output', 'value'),
    ],
)


# --------------------------------------------------------------------------
# 3. Fan-in: several sources converging on one node
# --------------------------------------------------------------------------

SCORING = document(
    'Weighted score',
    [
        node('customInput-1', 'customInput', (80, 100),
             inputName='quality', inputType='Number', inputValue='8'),
        node('customInput-2', 'customInput', (80, 320),
             inputName='weight', inputType='Number', inputValue='3'),
        node('math-1', 'math', (400, 200), operation='multiply', precision=0),
        node('condition-1', 'condition', (720, 200), expression='value >= 20'),
        node('text-1', 'text', (1040, 90), text='PASS with {{score}}'),
        node('text-2', 'text', (1040, 330), text='FAIL with {{score}}'),
        node('merge-1', 'merge', (1360, 200),
             strategy='concat', separator=' | ', inputCount=2),
        node('customOutput-1', 'customOutput', (1680, 200), outputName='verdict'),
    ],
    [
        edge('customInput-1', 'math-1', 'value', 'a'),
        edge('customInput-2', 'math-1', 'value', 'b'),
        edge('math-1', 'condition-1', 'result', 'value'),
        edge('condition-1', 'text-1', 'true', 'score'),
        edge('condition-1', 'text-2', 'false', 'score'),
        edge('text-1', 'merge-1', 'output', 'input_1'),
        edge('text-2', 'merge-1', 'output', 'input_2'),
        edge('merge-1', 'customOutput-1', 'merged', 'value'),
    ],
)


# --------------------------------------------------------------------------
# 4. A deliberately broken pipeline, for demonstrating the validator
# --------------------------------------------------------------------------

BROKEN = document(
    'Broken on purpose',
    [
        # A cycle between two Text nodes.
        node('text-1', 'text', (300, 100), text='{{in}}'),
        node('text-2', 'text', (620, 100), text='{{in}}'),
        # Math missing its second operand.
        node('customInput-1', 'customInput', (80, 320), inputValue='5'),
        node('math-1', 'math', (400, 320), operation='add'),
        # A variable nothing feeds.
        node('text-3', 'text', (400, 520), text='Hello {{nobody}}'),
        # Nothing connected at all.
        node('merge-1', 'merge', (80, 520), strategy='concat', inputCount=2),
    ],
    [
        edge('text-1', 'text-2', 'output', 'in'),
        edge('text-2', 'text-1', 'output', 'in'),
        edge('customInput-1', 'math-1', 'value', 'a'),
    ],
)


EXAMPLES = {
    'greeting.json': (GREETING, 'runs'),
    'ticket-triage.json': (TRIAGE, 'runs'),
    'weighted-score.json': (SCORING, 'runs'),
    'broken-on-purpose.json': (BROKEN, 'fails validation'),
}


def to_models(doc):
    nodes = [Node(id=n['id'], type=n['type'], data=n['data']) for n in doc['nodes']]
    edges = [Edge(**{k: e[k] for k in
                     ('id', 'source', 'target', 'sourceHandle', 'targetHandle')})
             for e in doc['edges']]
    return nodes, edges


def main() -> int:
    failures = 0

    for filename, (doc, expectation) in EXAMPLES.items():
        nodes, edges = to_models(doc)
        issues = validate(nodes, edges)
        broken = has_errors(issues)

        if expectation == 'runs':
            if broken:
                print('FAIL {}: expected to be valid, but: {}'.format(
                    filename, [i.message for i in issues if i.severity == 'error']))
                failures += 1
                continue
            report = execute(nodes, edges)
            if report.status != 'ok':
                print('FAIL {}: run reported {}'.format(filename, report.status))
                failures += 1
                continue
            print('ok   {:<24} -> {}'.format(filename, report.outputs))
        else:
            if not broken:
                print('FAIL {}: expected validation errors, found none'.format(filename))
                failures += 1
                continue
            codes = sorted({i.code for i in issues})
            print('ok   {:<24} -> {} issues: {}'.format(
                filename, len(issues), ', '.join(codes)))

        (HERE / filename).write_text(
            json.dumps(doc, indent=2) + '\n', encoding='utf-8')

    return failures


if __name__ == '__main__':
    raise SystemExit(main())
