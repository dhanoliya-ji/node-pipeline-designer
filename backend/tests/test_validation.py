"""Semantic validation: is the pipeline wired the way its nodes require."""

from conftest import edge, node

from app.core.validation import has_errors, validate


def codes(issues):
    return {issue.code for issue in issues}


def by_code(issues, code):
    return [issue for issue in issues if issue.code == code]


class TestCleanPipelines:
    def test_a_fully_wired_pipeline_has_no_errors(self, linear_pipeline):
        issues = validate(*linear_pipeline)
        assert not has_errors(issues), [i.message for i in issues]

    def test_an_empty_pipeline_is_informational_only(self):
        issues = validate([], [])
        assert codes(issues) == {'EMPTY_PIPELINE'}
        assert not has_errors(issues)

    def test_a_branching_pipeline_is_valid(self, branching_pipeline):
        assert not has_errors(validate(*branching_pipeline))


class TestStructuralErrors:
    def test_a_self_loop_is_reported_on_its_node(self):
        nodes = [node('text-1', 'text', text='hi')]
        issues = validate(nodes, [edge('text-1', 'text-1', 'output', 'x')])
        assert 'SELF_LOOP' in codes(issues)
        assert by_code(issues, 'SELF_LOOP')[0].node_id == 'text-1'

    def test_a_cycle_is_reported_on_every_node_it_contains(self):
        nodes = [node(n, 'text', text='{{in}}') for n in ('a', 'b')]
        edges = [
            edge('a', 'b', 'output', 'in'),
            edge('b', 'a', 'output', 'in'),
        ]
        issues = by_code(validate(nodes, edges), 'CYCLE')
        assert {i.node_id for i in issues} == {'a', 'b'}

    def test_a_long_cycle_abbreviates_its_message(self):
        """Naming every node of a 500-node ring in every issue was O(V^2)."""
        nodes = [node('n{}'.format(i), 'text', text='{{{{in}}}}') for i in range(500)]
        edges = [
            edge('n{}'.format(i), 'n{}'.format((i + 1) % 500), 'output', 'in')
            for i in range(500)
        ]
        issues = by_code(validate(nodes, edges), 'CYCLE')

        assert len(issues) == 500
        # Every issue shares one short sentence rather than a 500-id chain.
        assert len(issues[0].message) < 200
        assert 'more)' in issues[0].message

    def test_a_dangling_edge_is_reported(self):
        nodes = [node('customInput-1', 'customInput')]
        issues = validate(nodes, [edge('customInput-1', 'ghost', edge_id='e1')])
        assert 'DANGLING_EDGE' in codes(issues)

    def test_duplicate_node_ids_are_reported(self):
        nodes = [node('a', 'customInput'), node('a', 'customInput')]
        assert 'DUPLICATE_NODE_ID' in codes(validate(nodes, []))


class TestHandleErrors:
    def test_an_edge_onto_a_handle_that_does_not_exist(self):
        nodes = [
            node('customInput-1', 'customInput'),
            node('math-1', 'math'),
        ]
        edges = [edge('customInput-1', 'math-1', 'value', 'z')]
        assert 'UNKNOWN_TARGET_HANDLE' in codes(validate(nodes, edges))

    def test_an_edge_leaving_a_handle_that_does_not_exist(self):
        nodes = [
            node('customInput-1', 'customInput'),
            node('customOutput-1', 'customOutput'),
        ]
        edges = [edge('customInput-1', 'customOutput-1', 'nope', 'value')]
        assert 'UNKNOWN_SOURCE_HANDLE' in codes(validate(nodes, edges))

    def test_two_edges_into_one_input_is_ambiguous(self):
        nodes = [
            node('customInput-1', 'customInput'),
            node('customInput-2', 'customInput'),
            node('customOutput-1', 'customOutput'),
        ]
        edges = [
            edge('customInput-1', 'customOutput-1', 'value', 'value', 'e1'),
            edge('customInput-2', 'customOutput-1', 'value', 'value', 'e2'),
        ]
        assert 'AMBIGUOUS_INPUT' in codes(validate(nodes, edges))

    def test_fan_out_from_one_output_is_fine(self):
        """One source feeding several targets is normal, unlike fan-in."""
        nodes = [
            node('customInput-1', 'customInput'),
            node('customOutput-1', 'customOutput'),
            node('customOutput-2', 'customOutput'),
        ]
        edges = [
            edge('customInput-1', 'customOutput-1', 'value', 'value', 'e1'),
            edge('customInput-1', 'customOutput-2', 'value', 'value', 'e2'),
        ]
        assert 'AMBIGUOUS_INPUT' not in codes(validate(nodes, edges))

    def test_a_text_nodes_variable_handles_are_recognised(self):
        """The Text node's inputs come from its template, not a fixed list."""
        nodes = [
            node('customInput-1', 'customInput'),
            node('text-1', 'text', text='Dear {{title}} {{surname}}'),
        ]
        edges = [edge('customInput-1', 'text-1', 'value', 'surname')]
        assert 'UNKNOWN_TARGET_HANDLE' not in codes(validate(nodes, edges))

    def test_a_merge_nodes_handles_follow_its_input_count(self):
        nodes = [
            node('customInput-1', 'customInput'),
            node('merge-1', 'merge', strategy='concat', inputCount=3),
        ]
        edges = [edge('customInput-1', 'merge-1', 'value', 'input_3')]
        assert 'UNKNOWN_TARGET_HANDLE' not in codes(validate(nodes, edges))

    def test_a_merge_input_beyond_its_count_is_rejected(self):
        nodes = [
            node('customInput-1', 'customInput'),
            node('merge-1', 'merge', strategy='concat', inputCount=2),
        ]
        edges = [edge('customInput-1', 'merge-1', 'value', 'input_5')]
        assert 'UNKNOWN_TARGET_HANDLE' in codes(validate(nodes, edges))


class TestRequiredInputs:
    def test_a_missing_required_input_is_an_error(self):
        """Math needs both a and b; only a is connected here."""
        nodes = [
            node('customInput-1', 'customInput'),
            node('math-1', 'math', operation='add'),
        ]
        edges = [edge('customInput-1', 'math-1', 'value', 'a')]
        issues = by_code(validate(nodes, edges), 'MISSING_REQUIRED_INPUT')
        assert len(issues) == 1
        assert "'b'" in issues[0].message

    def test_an_optional_input_may_be_left_unconnected(self):
        """The LLM node's `system` handle is optional; `prompt` is not."""
        nodes = [
            node('text-1', 'text', text='hello'),
            node('llm-1', 'llm', model='gpt-4o'),
        ]
        edges = [edge('text-1', 'llm-1', 'output', 'prompt')]
        assert 'MISSING_REQUIRED_INPUT' not in codes(validate(nodes, edges))

    def test_an_api_node_without_a_url_is_an_error(self):
        nodes = [node('api-1', 'api', method='GET', url='')]
        assert 'MISSING_URL' in codes(validate(nodes, []))


class TestWarnings:
    def test_an_unconnected_text_variable_warns(self):
        nodes = [node('text-1', 'text', text='Hello {{name}}')]
        issues = by_code(validate(nodes, []), 'UNCONNECTED_VARIABLE')
        assert len(issues) == 1
        assert '{{name}}' in issues[0].message

    def test_an_isolated_node_warns(self):
        nodes = [
            node('customInput-1', 'customInput'),
            node('customOutput-1', 'customOutput'),
            node('math-1', 'math'),
        ]
        edges = [edge('customInput-1', 'customOutput-1', 'value', 'value')]
        issues = by_code(validate(nodes, edges), 'ISOLATED_NODE')
        assert [i.node_id for i in issues] == ['math-1']

    def test_a_pipeline_with_no_output_node_warns(self):
        nodes = [
            node('customInput-1', 'customInput'),
            node('text-1', 'text', text='{{v}}'),
        ]
        edges = [edge('customInput-1', 'text-1', 'value', 'v')]
        assert 'NO_OUTPUT_NODE' in codes(validate(nodes, edges))

    def test_an_unknown_node_type_warns_rather_than_failing(self):
        """A node the backend cannot run should not block the whole graph."""
        issues = validate([node('mystery-1', 'mystery')], [])
        assert 'UNKNOWN_NODE_TYPE' in codes(issues)
        assert not has_errors(issues)


class TestOrdering:
    def test_errors_are_listed_before_warnings(self):
        nodes = [
            node('math-1', 'math'),
            node('text-1', 'text', text='{{loose}}'),
        ]
        severities = [i.severity for i in validate(nodes, [])]
        assert severities == sorted(
            severities, key=lambda s: {'error': 0, 'warning': 1, 'info': 2}[s])
