# SPDX-FileCopyrightText: 2026 Manta contributors
#
# SPDX-License-Identifier: MIT

import pytest

from playbook.playbooks.expressions import (
    ExpressionError,
    Ref,
    check_expressions_in,
    evaluate,
    parse,
    refs,
    substitute,
)

SCOPE = {
    "inputs": {
        "solver": "highs",
        "years": 3,
        "target": 0.5,
        "enabled": True,
        "aggregate": {"snapshot": "resampled", "bus": None},
        "quoted": "it's",
    },
}


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("${{ inputs.solver }}", "highs"),
        ("${{inputs.solver}}", "highs"),
        ("${{ inputs.aggregate }}", {"snapshot": "resampled", "bus": None}),
        ("${{ inputs.aggregate.bus }}", None),
        ("${{ 'text' }}", "text"),
        ("${{ 'it''s' == inputs.quoted }}", True),
        ("${{ 42 }}", 42),
        ("${{ -1.5 }}", -1.5),
        ("${{ true }}", True),
        ("${{ null }}", None),
        ("${{ inputs.solver == 'highs' }}", True),
        ("${{ inputs.solver != 'highs' }}", False),
        ("${{ inputs.aggregate.snapshot != null }}", True),
        ("${{ inputs.aggregate.bus == null }}", True),
        ("${{ inputs.years > 2 }}", True),
        ("${{ inputs.years <= 2 }}", False),
        ("${{ inputs.target >= 0.5 }}", True),
        ("${{ inputs.target < 1 }}", True),
        ("${{ 'a' < 'b' }}", True),
        ("${{ !inputs.enabled }}", False),
        ("${{ !!inputs.solver }}", True),
        ("${{ inputs.enabled && inputs.years == 3 }}", True),
        ("${{ inputs.enabled && inputs.aggregate.bus }}", False),
        ("${{ inputs.aggregate.bus || inputs.solver }}", True),
        ("${{ false || false || true }}", True),
        ("${{ true || false && false }}", True),
        ("${{ (true || false) && false }}", False),
        ("${{ !(inputs.years == 3) }}", False),
    ],
)
def test_an_expression_evaluates_to_its_value(text, expected):
    assert evaluate(parse(text), SCOPE) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("${{ 1 }}", set()),
        ("${{ inputs.aggregate.snapshot }}", {Ref("inputs", ("aggregate", "snapshot"))}),
        (
            "${{ inputs.solver == 'w1' && !inputs.enabled }}",
            {Ref("inputs", ("solver",)), Ref("inputs", ("enabled",))},
        ),
    ],
)
def test_refs_lists_what_an_expression_reads(text, expected):
    assert refs(parse(text)) == expected


@pytest.mark.parametrize(
    "text",
    [
        "inputs.solver",
        "${{ }}",
        "${{ inputs. }}",
        "${{ inputs.1 }}",
        "${{ matrix.scenario }}",
        "${{ dims.scenario }}",
        "${{ secrets.token }}",
        "${{ inputs.solver == }}",
        "${{ inputs.solver = 'highs' }}",
        "${{ (inputs.solver }}",
        "${{ inputs.solver) }}",
        "${{ 'unterminated }}",
        "${{ inputs.solver 'highs' }}",
        "${{ 1 < 2 < 3 }}",
        "${{ inputs.a + 1 }}",
    ],
)
def test_a_malformed_expression_is_refused(text):
    with pytest.raises(ExpressionError):
        parse(text)


@pytest.mark.parametrize(
    "text",
    [
        "${{ inputs.a }} and more",
        "prefix ${{ inputs.a }}",
        "${{ inputs.a }} and ${{ inputs.b }}",
        "${{ inputs.a }}${{ inputs.b }}",
    ],
)
def test_text_around_an_expression_is_named_as_such(text):
    with pytest.raises(ExpressionError, match="mixes an expression with other text"):
        parse(text)


@pytest.mark.parametrize(
    "text",
    [
        "${{ inputs.missing }}",
        "${{ inputs.solver.name }}",
        "${{ inputs.aggregate.bus < 1 }}",
        "${{ inputs.solver > 1 }}",
    ],
)
def test_an_expression_that_cannot_be_evaluated_is_refused(text):
    with pytest.raises(ExpressionError):
        evaluate(parse(text), SCOPE)


def test_substitute_evaluates_every_expression_and_keeps_its_type():
    value = {
        "method": "resample",
        "resolution": "${{ inputs.years }}",
        "aggregation": {"snapshot": "weekly", "bus": "${{ inputs.aggregate.bus }}"},
        "metrics": ["lole", "${{ inputs.solver }}"],
        "enabled": "${{ inputs.enabled }}",
        "size": 4,
    }
    assert substitute(value, SCOPE) == {
        "method": "resample",
        "resolution": 3,
        "aggregation": {"snapshot": "weekly", "bus": None},
        "metrics": ["lole", "highs"],
        "enabled": True,
        "size": 4,
    }


def test_substitute_evaluates_an_already_parsed_expression():
    assert substitute({"solver": parse("${{ inputs.solver }}")}, SCOPE) == {"solver": "highs"}


@pytest.mark.parametrize(
    "value",
    [{"resolution": "every ${{ inputs.years }}h"}, ["${{ inputs.years }}", ["${{ oops }}"]]],
)
def test_text_holding_a_broken_expression_is_refused_wherever_it_sits(value):
    with pytest.raises(ExpressionError):
        check_expressions_in(value)
