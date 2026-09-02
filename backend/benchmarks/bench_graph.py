"""Benchmarks for the graph pipeline.

Measures the three things the README claims:

  1. `analyse` is O(V + E) — the topological pass, cycle search and shape
     metrics together.
  2. `validate` adds a constant factor on top of it, not another order.
  3. `execute` costs what analysis costs plus the handlers' own work.

Run it directly to write `benchmarks/results.csv`, which
`notebooks/analysis.ipynb` reads and plots:

    python -m benchmarks.bench_graph

Each configuration is timed several times and the *median* is kept, because
a laptop under load produces occasional outliers an order of magnitude above
the true cost and a mean would carry them straight into the chart.
"""

import csv
import random
import statistics
import sys
import time
from pathlib import Path
from typing import Callable, List, Sequence, Tuple

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.engine import execute  # noqa: E402
from app.core.graph import analyse  # noqa: E402
from app.core.validation import validate  # noqa: E402
from app.schemas import Edge, Node  # noqa: E402

REPEATS = 7
SIZES = [10, 25, 50, 100, 250, 500, 1000, 2000]
RESULTS = Path(__file__).resolve().parent / 'results.csv'


# --------------------------------------------------------------------------
# Graph generators
# --------------------------------------------------------------------------

def make_chain(size: int) -> Tuple[List[Node], List[Edge]]:
    """The thinnest possible pipeline: E = V - 1, depth = V."""
    nodes = [Node(id='n{}'.format(i), type='text', data={'text': 'x'})
             for i in range(size)]
    edges = [
        Edge(id='e{}'.format(i), source='n{}'.format(i), target='n{}'.format(i + 1))
        for i in range(size - 1)
    ]
    return nodes, edges


def make_layered(size: int, width: int = 5) -> Tuple[List[Node], List[Edge]]:
    """A realistic pipeline shape: fixed-width layers, fully connected between.

    Edge count grows as width x V, so this is the case that separates an
    O(V + E) implementation from an O(V x E) one.
    """
    nodes = [Node(id='n{}'.format(i), type='text', data={'text': 'x'})
             for i in range(size)]
    edges = []
    for i in range(size):
        for offset in range(1, width + 1):
            target = i + offset
            if target < size and (i // width) != (target // width):
                edges.append(Edge(
                    id='e{}-{}'.format(i, target),
                    source='n{}'.format(i),
                    target='n{}'.format(target),
                ))
    return nodes, edges


def make_random_dag(size: int, density: float = 2.0, seed: int = 7):
    """Random edges that always point forwards, so the result is acyclic."""
    rng = random.Random(seed)
    nodes = [Node(id='n{}'.format(i), type='text', data={'text': 'x'})
             for i in range(size)]
    edges = []
    for target in range(1, size):
        for _ in range(max(1, int(density))):
            source = rng.randrange(0, target)
            edges.append(Edge(
                id='e{}-{}-{}'.format(source, target, len(edges)),
                source='n{}'.format(source),
                target='n{}'.format(target),
            ))
    return nodes, edges


def make_ring(size: int) -> Tuple[List[Node], List[Edge]]:
    """The worst case for cycle reporting: every node is on one long cycle."""
    nodes, edges = make_chain(size)
    edges.append(Edge(id='eclose', source='n{}'.format(size - 1), target='n0'))
    return nodes, edges


def make_runnable(size: int) -> Tuple[List[Node], List[Edge]]:
    """An executable chain: Input -> Text -> Text -> ... -> Output."""
    nodes: List[Node] = [Node(
        id='customInput-1',
        type='customInput',
        data={'inputName': 'seed', 'inputType': 'Text', 'inputValue': 'x'},
    )]
    edges: List[Edge] = []
    previous, previous_handle = 'customInput-1', 'value'

    for i in range(size - 2):
        node_id = 'text-{}'.format(i + 1)
        nodes.append(Node(id=node_id, type='text', data={'text': '{{v}}!'}))
        edges.append(Edge(
            id='e{}'.format(i),
            source=previous,
            target=node_id,
            sourceHandle='{}-{}'.format(previous, previous_handle),
            targetHandle='{}-v'.format(node_id),
        ))
        previous, previous_handle = node_id, 'output'

    nodes.append(Node(id='customOutput-1', type='customOutput',
                      data={'outputName': 'result'}))
    edges.append(Edge(
        id='efinal',
        source=previous,
        target='customOutput-1',
        sourceHandle='{}-{}'.format(previous, previous_handle),
        targetHandle='customOutput-1-value',
    ))
    return nodes, edges


# --------------------------------------------------------------------------
# Timing
# --------------------------------------------------------------------------

def time_median(call: Callable[[], object], repeats: int = REPEATS) -> float:
    """Median wall-clock milliseconds over `repeats` runs."""
    timings = []
    for _ in range(repeats):
        started = time.perf_counter()
        call()
        timings.append((time.perf_counter() - started) * 1000)
    return statistics.median(timings)


def run() -> List[dict]:
    generators = {
        'chain': make_chain,
        'layered': make_layered,
        'random_dag': make_random_dag,
        'ring': make_ring,
    }

    rows: List[dict] = []

    for shape, generate in generators.items():
        for size in SIZES:
            nodes, edges = generate(size)
            row = {
                'shape': shape,
                'nodes': len(nodes),
                'edges': len(edges),
                'analyse_ms': time_median(lambda: analyse(nodes, edges)),
                'validate_ms': time_median(lambda: validate(nodes, edges)),
            }
            row['total_ms'] = row['analyse_ms'] + row['validate_ms']
            rows.append(row)
            print('{:>11} {:>5} nodes {:>6} edges  analyse {:7.3f} ms  '
                  'validate {:7.3f} ms'.format(
                      shape, row['nodes'], row['edges'],
                      row['analyse_ms'], row['validate_ms']))

    # Execution is measured separately: only a runnable pipeline can be run,
    # and its cost includes the handlers, not just the graph pass.
    for size in SIZES:
        nodes, edges = make_runnable(size)
        rows.append({
            'shape': 'execute',
            'nodes': len(nodes),
            'edges': len(edges),
            'analyse_ms': time_median(lambda: analyse(nodes, edges)),
            'validate_ms': time_median(lambda: validate(nodes, edges)),
            'total_ms': time_median(lambda: execute(nodes, edges, strict=False)),
        })
        print('{:>11} {:>5} nodes  execute {:7.3f} ms'.format(
            'execute', len(nodes), rows[-1]['total_ms']))

    return rows


def write(rows: Sequence[dict], path: Path = RESULTS) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=['shape', 'nodes', 'edges', 'analyse_ms',
                        'validate_ms', 'total_ms'],
        )
        writer.writeheader()
        writer.writerows(rows)
    return path


if __name__ == '__main__':
    written = write(run())
    print('\nWrote {} rows to {}'.format(len(list(open(written))) - 1, written))
