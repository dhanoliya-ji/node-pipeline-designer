"""The sandboxed expression evaluator used by the branching nodes."""

import pytest

from app.core.expressions import ExpressionError, evaluate, evaluate_truthy


class TestSupportedExpressions:
    @pytest.mark.parametrize('expression, expected', [
        ('1 + 1', 2),
        ('10 - 4', 6),
        ('3 * 4', 12),
        ('10 / 4', 2.5),
        ('10 // 4', 2),
        ('10 % 3', 1),
        ('2 ** 8', 256),
        ('-5', -5),
    ])
    def test_arithmetic(self, expression, expected):
        assert evaluate(expression, {}) == expected

    @pytest.mark.parametrize('expression, expected', [
        ('value > 10', True),
        ('value < 10', False),
        ('value == 42', True),
        ('value != 42', False),
        ('value >= 42', True),
        ('0 < value < 100', True),
    ])
    def test_comparisons_against_a_supplied_name(self, expression, expected):
        assert evaluate(expression, {'value': 42}) == expected

    def test_boolean_operators(self):
        names = {'value': 5}
        assert evaluate('value > 1 and value < 10', names) is True
        assert evaluate('value > 10 or value == 5', names) is True

    def test_boolean_operators_return_the_deciding_operand(self):
        """`or` yields the first truthy operand, as it does in Python."""
        assert evaluate('0 or value', {'value': 'fallback'}) == 'fallback'
        assert evaluate('value and 0', {'value': 'set'}) == 0

    def test_membership(self):
        assert evaluate('"urgent" in value', {'value': 'an urgent ticket'}) is True
        assert evaluate('"calm" not in value', {'value': 'an urgent ticket'}) is True

    def test_whitelisted_functions(self):
        assert evaluate('len(value)', {'value': 'abcd'}) == 4
        assert evaluate('upper(value)', {'value': 'hi'}) == 'HI'
        assert evaluate('round(value, 1)', {'value': 3.14159}) == 3.1
        assert evaluate('max(1, 7, 3)', {}) == 7

    def test_conditional_expression(self):
        assert evaluate('1 if value else 0', {'value': True}) == 1

    def test_list_literal_and_membership(self):
        assert evaluate('value in ["a", "b"]', {'value': 'b'}) is True

    def test_chained_comparison_short_circuits_correctly(self):
        assert evaluate('1 < 5 < 2', {}) is False


class TestRejectedExpressions:
    @pytest.mark.parametrize('expression', [
        '__import__("os").system("echo hi")',
        'open("/etc/passwd").read()',
        'value.__class__',
        'value.upper()',
        '[].__class__.__base__',
        'exec("x=1")',
        'lambda: 1',
        '{"a": 1}["a"]',
        'value[0]',
        'globals()',
    ])
    def test_dangerous_constructs_are_refused(self, expression):
        """Nothing here should reach the interpreter's real namespace."""
        with pytest.raises(ExpressionError):
            evaluate(expression, {'value': 'text'})

    def test_unknown_name_is_refused(self):
        with pytest.raises(ExpressionError, match='unknown name'):
            evaluate('secret > 1', {'value': 1})

    def test_unknown_function_is_refused(self):
        with pytest.raises(ExpressionError, match='unknown function'):
            evaluate('eval("1")', {})

    def test_syntax_error_is_reported_readably(self):
        with pytest.raises(ExpressionError, match='syntax error'):
            evaluate('value >', {'value': 1})

    def test_empty_expression_is_refused(self):
        with pytest.raises(ExpressionError, match='empty'):
            evaluate('   ', {})

    def test_division_by_zero_is_a_readable_error(self):
        with pytest.raises(ExpressionError, match='division by zero'):
            evaluate('1 / 0', {})

    def test_overlong_expression_is_refused(self):
        with pytest.raises(ExpressionError, match='exceeds'):
            evaluate('1 + ' * 400 + '1', {})


class TestTruthiness:
    @pytest.mark.parametrize('value, expected', [
        ('non-empty', True),
        ('', False),
        (0, False),
        (7, True),
        ([], False),
    ])
    def test_values_coerce_to_a_bool(self, value, expected):
        assert evaluate_truthy('value', {'value': value}) is expected
