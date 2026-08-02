import ast

from scripts.policy_lint import default_assignments, is_default_like, is_membership_test


def test_membership_ternary_default_is_detectable():
    expression = ast.parse("value = values[key] if key in values else []").body[0].value

    assert isinstance(expression, ast.IfExp)
    assert is_membership_test(expression.test)
    assert is_default_like(expression.orelse)


def test_membership_branch_default_assignment_is_detectable():
    statement = ast.parse(
        """
if key in values:
    value = values[key]
else:
    value = []
"""
    ).body[0]

    assert isinstance(statement, ast.If)
    assert is_membership_test(statement.test)
    assert default_assignments(statement.orelse) == {'value'}