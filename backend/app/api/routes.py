"""HTTP surface.

Four endpoints, each a thin adapter over `app.core`:

    GET  /health            liveness, and the node types this build can run
    GET  /nodes             the executable node catalogue
    POST /pipelines/parse   structure + validation of a submitted pipeline
    POST /pipelines/validate  just the validation report
    POST /pipelines/execute   run the pipeline and report every step

`/pipelines/parse` is the endpoint the original build shipped, and its
`num_nodes` / `num_edges` / `is_dag` fields are unchanged - the extra fields
are additive so an older client keeps working.
"""

from fastapi import APIRouter, HTTPException

from ..core.engine import PipelineTooLarge, execute
from ..core.graph import analyse
from ..core.validation import has_errors, validate
from ..nodes import all_specs
from ..schemas import (
    ExecutionReport,
    NodeDescriptor,
    Pipeline,
    PipelineStats,
    ValidationReport,
)

router = APIRouter()


@router.get('/health', tags=['meta'])
def health() -> dict:
    return {'status': 'ok', 'node_types': len(all_specs())}


@router.get('/nodes', response_model=list[NodeDescriptor], tags=['meta'])
def list_nodes() -> list[NodeDescriptor]:
    """The node types the engine can run, for clients that build a palette."""
    return [
        NodeDescriptor(
            type=spec.type,
            label=spec.label,
            description=spec.description,
            # Dynamic handles depend on a node's data, so a spec with no
            # static inputs reports an empty list here rather than guessing.
            inputs=spec.input_handles(),
            outputs=spec.output_handles(),
            executable=spec.executable,
        )
        for spec in all_specs()
    ]


@router.post('/pipelines/parse', response_model=PipelineStats, tags=['pipelines'])
def parse_pipeline(pipeline: Pipeline) -> PipelineStats:
    """Report a pipeline's size, structure and problems."""
    analysis = analyse(pipeline.nodes, pipeline.edges)
    issues = validate(pipeline.nodes, pipeline.edges, analysis)

    return PipelineStats(
        num_nodes=len(pipeline.nodes),
        num_edges=len(pipeline.edges),
        is_dag=analysis.is_dag,
        cycles=analysis.cycles,
        topological_order=analysis.topological_order,
        depth=analysis.depth,
        entry_points=analysis.entry_points,
        exit_points=analysis.exit_points,
        isolated_nodes=analysis.isolated_nodes,
        issues=issues,
    )


@router.post('/pipelines/validate', response_model=ValidationReport, tags=['pipelines'])
def validate_pipeline(pipeline: Pipeline) -> ValidationReport:
    analysis = analyse(pipeline.nodes, pipeline.edges)
    issues = validate(pipeline.nodes, pipeline.edges, analysis)

    return ValidationReport(
        is_dag=analysis.is_dag,
        is_valid=analysis.is_dag and not has_errors(issues),
        issues=issues,
        topological_order=analysis.topological_order,
    )


@router.post('/pipelines/execute', response_model=ExecutionReport, tags=['pipelines'])
def execute_pipeline(pipeline: Pipeline, strict: bool = True) -> ExecutionReport:
    """Run the pipeline.

    A pipeline that fails validation is refused with its issues attached
    rather than half-run; pass `?strict=false` to run whatever is runnable.
    """
    try:
        return execute(pipeline.nodes, pipeline.edges, strict=strict)
    except PipelineTooLarge as error:
        raise HTTPException(status_code=413, detail=str(error))
