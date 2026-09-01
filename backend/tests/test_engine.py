"""The execution engine, and the node handlers it drives."""

import pytest
from conftest import edge, node

from app.core.engine import PipelineTooLarge, execute
from app.nodes import extract_variables
from app.nodes.handlers import (
    NodeExecutionError,
    run_filter,
    run_llm,
    run_math,
    run_merge,
    run_text,
)


def step_for(report, node_id):
    return next(s for s in report.steps if s.node_id == node_id)


class TestEndToEnd:
    def test_a_linear_pipeline_produces_its_output(self, linear_pipeline):
        report = execute(*linear_pipeline)
        assert report.status == 'ok'
        assert report.outputs == {'greeting': 'Hello, Ada!'}

    def test_every_node_reports_a_step(self, linear_pipeline):
        report = execute(*linear_pipeline)
        assert len(report.steps) == 3
        assert all(s.status == 'ok' for s in report.steps)

    def test_nodes_run_in_topological_order(self, linear_pipeline):
        order = [s.node_id for s in execute(*linear_pipeline).steps]
        assert order == ['customInput-1', 'text-1', 'customOutput-1']

    def test_the_run_is_timed(self, linear_pipeline):
        report = execute(*linear_pipeline)
        assert report.duration_ms >= 0

    def test_an_empty_pipeline_runs_and_produces_nothing(self):
        report = execute([], [])
        assert report.status == 'ok'
        assert report.outputs == {}


class TestRefusals:
    def test_a_cyclic_pipeline_is_refused_before_anything_runs(self):
        nodes = [node(n, 'text', text='{{in}}') for n in ('a', 'b')]
        edges = [
            edge('a', 'b', 'output', 'in'),
            edge('b', 'a', 'output', 'in'),
        ]
        report = execute(nodes, edges)
        assert report.status == 'error'
        assert report.steps == []
        assert any(i.code == 'CYCLE' for i in report.issues)

    def test_a_pipeline_with_validation_errors_is_refused_in_strict_mode(self):
        nodes = [
            node('customInput-1', 'customInput', inputValue='1'),
            node('math-1', 'math', operation='add'),
        ]
        edges = [edge('customInput-1', 'math-1', 'value', 'a')]
        assert execute(nodes, edges, strict=True).status == 'error'

    def test_non_strict_mode_runs_what_it_can(self):
        nodes = [
            node('customInput-1', 'customInput', inputValue='1'),
            node('math-1', 'math', operation='add'),
        ]
        edges = [edge('customInput-1', 'math-1', 'value', 'a')]
        report = execute(nodes, edges, strict=False)
        # `b` defaults to 0, so add still produces a result.
        assert step_for(report, 'math-1').outputs == {'result': 1.0}

    def test_an_oversized_pipeline_is_refused(self, monkeypatch):
        monkeypatch.setattr('app.core.engine.MAX_NODES', 2)
        with pytest.raises(PipelineTooLarge):
            execute([node('a'), node('b'), node('c')], [], strict=False)


class TestBranching:
    def test_only_the_taken_branch_produces_an_output(self, branching_pipeline):
        """score is 75, so `value > 50` is true and only `high` is filled."""
        report = execute(*branching_pipeline)
        assert report.outputs == {'high': 75.0}

    def test_the_untaken_branch_is_skipped_not_failed(self, branching_pipeline):
        report = execute(*branching_pipeline)
        assert step_for(report, 'customOutput-2').status == 'skipped'
        assert report.status == 'ok'

    def test_the_other_branch_is_taken_when_the_condition_flips(self, branching_pipeline):
        nodes, edges = branching_pipeline
        nodes[0].data['inputValue'] = '20'
        report = execute(nodes, edges)
        assert report.outputs == {'low': 20.0}
        assert step_for(report, 'customOutput-1').status == 'skipped'

    def test_a_skip_propagates_down_the_whole_subtree(self):
        """Nothing past an untaken branch should run."""
        nodes = [
            node('customInput-1', 'customInput', inputValue='hello'),
            node('filter-1', 'filter', operator='contains', operand='zzz'),
            node('text-1', 'text', text='got {{v}}'),
            node('customOutput-1', 'customOutput', outputName='out'),
        ]
        edges = [
            edge('customInput-1', 'filter-1', 'value', 'input'),
            edge('filter-1', 'text-1', 'pass', 'v'),
            edge('text-1', 'customOutput-1', 'output', 'value'),
        ]
        report = execute(nodes, edges)
        assert step_for(report, 'text-1').status == 'skipped'
        assert step_for(report, 'customOutput-1').status == 'skipped'
        assert report.outputs == {}


class TestFailures:
    def test_a_failing_node_marks_the_run_as_errored(self):
        nodes = [
            node('customInput-1', 'customInput', inputValue='7'),
            node('customInput-2', 'customInput', inputValue='0'),
            node('math-1', 'math', operation='divide'),
            node('customOutput-1', 'customOutput', outputName='out'),
        ]
        edges = [
            edge('customInput-1', 'math-1', 'value', 'a'),
            edge('customInput-2', 'math-1', 'value', 'b'),
            edge('math-1', 'customOutput-1', 'result', 'value'),
        ]
        report = execute(nodes, edges)
        assert report.status == 'error'
        assert step_for(report, 'math-1').status == 'error'
        assert 'division by zero' in step_for(report, 'math-1').message

    def test_a_failure_does_not_run_the_nodes_below_it(self):
        nodes = [
            node('customInput-1', 'customInput', inputValue='7'),
            node('customInput-2', 'customInput', inputValue='0'),
            node('math-1', 'math', operation='divide'),
            node('customOutput-1', 'customOutput', outputName='out'),
        ]
        edges = [
            edge('customInput-1', 'math-1', 'value', 'a'),
            edge('customInput-2', 'math-1', 'value', 'b'),
            edge('math-1', 'customOutput-1', 'result', 'value'),
        ]
        report = execute(nodes, edges)
        assert step_for(report, 'customOutput-1').status == 'skipped'

    def test_an_unknown_node_type_is_skipped_not_fatal(self):
        nodes = [node('mystery-1', 'mystery')]
        report = execute(nodes, [], strict=False)
        assert step_for(report, 'mystery-1').status == 'skipped'
        assert report.status == 'ok'


class TestDataFlow:
    def test_a_value_reaches_several_targets(self):
        nodes = [
            node('customInput-1', 'customInput', inputValue='x'),
            node('customOutput-1', 'customOutput', outputName='a'),
            node('customOutput-2', 'customOutput', outputName='b'),
        ]
        edges = [
            edge('customInput-1', 'customOutput-1', 'value', 'value', 'e1'),
            edge('customInput-1', 'customOutput-2', 'value', 'value', 'e2'),
        ]
        assert execute(nodes, edges).outputs == {'a': 'x', 'b': 'x'}

    def test_a_diamond_converges_on_one_node(self):
        nodes = [
            node('customInput-1', 'customInput', inputType='Number', inputValue='4'),
            node('math-1', 'math', operation='multiply', precision=0),
            node('customOutput-1', 'customOutput', outputName='squared'),
        ]
        edges = [
            edge('customInput-1', 'math-1', 'value', 'a', 'e1'),
            edge('customInput-1', 'math-1', 'value', 'b', 'e2'),
            edge('math-1', 'customOutput-1', 'result', 'value'),
        ]
        assert execute(nodes, edges).outputs == {'squared': 16}

    def test_several_stages_chain_their_values(self):
        nodes = [
            node('customInput-1', 'customInput', inputValue='world'),
            node('text-1', 'text', text='hello {{name}}'),
            node('text-2', 'text', text='<<{{inner}}>>'),
            node('customOutput-1', 'customOutput', outputName='final'),
        ]
        edges = [
            edge('customInput-1', 'text-1', 'value', 'name'),
            edge('text-1', 'text-2', 'output', 'inner'),
            edge('text-2', 'customOutput-1', 'output', 'value'),
        ]
        assert execute(nodes, edges).outputs == {'final': '<<hello world>>'}

    def test_an_isolated_node_still_runs_but_feeds_nothing(self):
        nodes = [
            node('customInput-1', 'customInput', inputValue='alone'),
        ]
        report = execute(nodes, [], strict=False)
        assert step_for(report, 'customInput-1').status == 'ok'
        assert report.outputs == {}


class TestTextHandler:
    def test_variables_are_substituted(self):
        assert run_text({'text': 'Hi {{a}} and {{b}}'}, {'a': '1', 'b': '2'}) == {
            'output': 'Hi 1 and 2'}

    def test_an_unconnected_variable_is_left_visible(self):
        assert run_text({'text': 'Hi {{a}}'}, {}) == {'output': 'Hi {{a}}'}

    def test_a_repeated_variable_is_substituted_everywhere(self):
        assert run_text({'text': '{{a}}-{{a}}'}, {'a': 'x'}) == {'output': 'x-x'}

    def test_a_template_with_no_variables_passes_through(self):
        assert run_text({'text': 'plain'}, {}) == {'output': 'plain'}

    @pytest.mark.parametrize('template, expected', [
        ('{{a}}', ['a']),
        ('{{ a }}', ['a']),
        ('{{a}} {{b}} {{a}}', ['a', 'b']),
        ('{{ _private }}', ['_private']),
        ('{{1bad}}', []),
        ('{{a b}}', []),
        ('{ a }', []),
        ('', []),
        (None, []),
    ])
    def test_variable_extraction_matches_the_frontend_rules(self, template, expected):
        assert extract_variables(template) == expected


class TestMathHandler:
    @pytest.mark.parametrize('operation, expected', [
        ('add', 7.0),
        ('subtract', 3.0),
        ('multiply', 10.0),
        ('divide', 2.5),
    ])
    def test_each_operation(self, operation, expected):
        assert run_math({'operation': operation}, {'a': 5, 'b': 2}) == {
            'result': expected}

    def test_numeric_strings_are_accepted(self):
        assert run_math({'operation': 'add'}, {'a': '5', 'b': '2'})['result'] == 7.0

    def test_a_non_numeric_input_fails_with_a_readable_message(self):
        with pytest.raises(NodeExecutionError, match='not a number'):
            run_math({'operation': 'add'}, {'a': 'abc', 'b': 1})

    def test_precision_is_applied(self):
        result = run_math({'operation': 'divide', 'precision': 3}, {'a': 1, 'b': 3})
        assert result == {'result': 0.333}

    def test_zero_precision_yields_a_whole_number(self):
        assert run_math({'operation': 'divide', 'precision': 0}, {'a': 7, 'b': 2}) == {
            'result': 4}


class TestFilterHandler:
    def test_a_match_takes_the_pass_branch(self):
        result = run_filter({'operator': 'contains', 'operand': 'urg'},
                            {'input': 'urgent'})
        assert result == {'pass': 'urgent'}

    def test_a_miss_takes_the_fail_branch(self):
        result = run_filter({'operator': 'contains', 'operand': 'zzz'},
                            {'input': 'urgent'})
        assert result == {'fail': 'urgent'}

    def test_matching_is_case_insensitive_by_default(self):
        assert 'pass' in run_filter({'operator': 'equals', 'operand': 'YES'},
                                    {'input': 'yes'})

    def test_case_sensitivity_can_be_turned_on(self):
        assert 'fail' in run_filter(
            {'operator': 'equals', 'operand': 'YES', 'caseSensitive': True},
            {'input': 'yes'})

    def test_regex_matching(self):
        assert 'pass' in run_filter({'operator': 'matches', 'operand': r'^\d{3}$'},
                                    {'input': '123'})

    def test_an_invalid_regex_fails_readably(self):
        with pytest.raises(NodeExecutionError, match='invalid regular expression'):
            run_filter({'operator': 'matches', 'operand': '['}, {'input': 'x'})


class TestMergeHandler:
    def test_concat_joins_with_the_separator(self):
        result = run_merge({'strategy': 'concat', 'separator': ', ', 'inputCount': 2},
                           {'input_1': 'a', 'input_2': 'b'})
        assert result == {'merged': 'a, b'}

    def test_an_escaped_newline_separator_becomes_a_real_newline(self):
        result = run_merge({'strategy': 'concat', 'separator': '\\n', 'inputCount': 2},
                           {'input_1': 'a', 'input_2': 'b'})
        assert result == {'merged': 'a\nb'}

    def test_array_strategy_collects_the_values(self):
        result = run_merge({'strategy': 'array', 'inputCount': 2},
                           {'input_1': 1, 'input_2': 2})
        assert result == {'merged': [1, 2]}

    def test_object_strategy_keys_by_handle(self):
        result = run_merge({'strategy': 'object', 'inputCount': 2},
                           {'input_1': 1, 'input_2': 2})
        assert result == {'merged': {'input_1': 1, 'input_2': 2}}

    def test_unconnected_inputs_are_skipped(self):
        result = run_merge({'strategy': 'array', 'inputCount': 3},
                           {'input_1': 'a', 'input_3': 'c'})
        assert result == {'merged': ['a', 'c']}

    def test_values_are_joined_in_handle_order_not_arrival_order(self):
        result = run_merge({'strategy': 'concat', 'separator': '-', 'inputCount': 3},
                           {'input_3': 'c', 'input_1': 'a', 'input_2': 'b'})
        assert result == {'merged': 'a-b-c'}


class TestLlmHandler:
    def test_the_response_is_labelled_as_simulated(self):
        result = run_llm({'model': 'gpt-4o'}, {'prompt': 'hi'})
        assert 'simulated' in result['response']
        assert result['_meta']['simulated'] is True

    def test_the_prompt_is_echoed(self):
        assert 'hi there' in run_llm({}, {'prompt': 'hi there'})['response']

    def test_metadata_is_hidden_from_the_reported_outputs(self):
        """Keys starting with an underscore are engine metadata, not handles."""
        nodes = [
            node('text-1', 'text', text='hello'),
            node('llm-1', 'llm', model='gpt-4o'),
        ]
        edges = [edge('text-1', 'llm-1', 'output', 'prompt')]
        report = execute(nodes, edges, strict=False)
        assert set(step_for(report, 'llm-1').outputs) == {'response'}


class TestApiHandler:
    def test_outbound_http_is_disabled_by_default(self):
        nodes = [node('api-1', 'api', method='GET', url='https://example.com')]
        report = execute(nodes, [], strict=False)
        assert 'disabled' in step_for(report, 'api-1').outputs['error']

    def test_a_node_with_no_url_reports_it(self):
        nodes = [node('api-1', 'api', method='GET', url='')]
        report = execute(nodes, [], strict=False)
        assert step_for(report, 'api-1').outputs == {'error': 'no URL configured'}
