import typing

import pytest
from beancount_parser.parser import make_parser
from lark import Token
from lark import Tree

from beancount_black.formater import format_comment
from beancount_black.formater import format_cost
from beancount_black.formater import format_date_directive
from beancount_black.formater import format_number
from beancount_black.formater import format_price


@pytest.mark.parametrize(
    "value, expected_result",
    [
        ("*", "*"),
        (";", ";"),
        ("; ", ";"),
        (";; ", ";;"),
        ("; comment", "; comment"),
        ("*comment", "* comment"),
        (" *comment ", "* comment"),
        (";comment  ", "; comment"),
        (";;comment", ";; comment"),
        (";;;comment", ";;; comment"),
        (";;; ;comment", ";;; ;comment"),
        (
            ";;-*- mode: org; mode: beancount; -*-",
            ";; -*- mode: org; mode: beancount; -*-",
        ),
    ],
)
def test_format_comment(value: str, expected_result: str):
    token = Token("COMMENT", value=value)
    assert format_comment(token) == expected_result


@pytest.mark.parametrize(
    "value, expected_result",
    [
        ("+123.4567", "123.4567"),
        ("-123.4567", "-123.4567"),
        ("1234567.90", "1,234,567.90"),
    ],
)
def test_format_number(value: str, expected_result: str):
    token = Token("SIGNED_NUMBER", value=value)
    assert format_number(token) == expected_result


@pytest.mark.parametrize(
    "column_widths, text, expected_result",
    [
        (
            None,
            "1970-01-01  open     Assets:Bank",
            "1970-01-01 open Assets:Bank",
        ),
        (
            None,
            "1970-01-01  open     Assets:Bank   USD",
            "1970-01-01 open Assets:Bank USD",
        ),
        (
            None,
            "1970-01-01  open     Assets:Bank   USD,BTC",
            "1970-01-01 open Assets:Bank USD,BTC",
        ),
        (
            None,
            '1970-01-01  open     Assets:Bank   USD,BTC  "strict" ',
            '1970-01-01 open Assets:Bank USD,BTC "strict"',
        ),
        (
            None,
            "1970-01-01  close     Assets:Bank",
            "1970-01-01 close Assets:Bank",
        ),
        (
            dict(balance={2: "20", 3: ">10"}),
            "1970-01-01  balance     Assets:Bank  12.34    USD",
            "1970-01-01 balance Assets:Bank               12.34 USD",
        ),
    ],
)
def test_format_date_directive(
    column_widths: typing.Optional[typing.Dict], text: str, expected_result: str
):
    parser = make_parser()
    root = parser.parse(text)
    date_directive = root.children[0]
    assert (
        format_date_directive(date_directive, column_widths=column_widths)
        == expected_result
    )


@pytest.mark.parametrize(
    "tree, expected_result",
    [
        (
            Tree(
                "per_unit_price",
                [
                    Tree(
                        "amount",
                        [Token("SIGNED_NUMBER", "1234.56"), Token("CURRENCY", "USD")],
                    )
                ],
            ),
            "@ 1,234.56 USD",
        ),
        (
            Tree(
                "total_price",
                [
                    Tree(
                        "amount",
                        [Token("SIGNED_NUMBER", "1234.56"), Token("CURRENCY", "USD")],
                    )
                ],
            ),
            "@@ 1,234.56 USD",
        ),
    ],
)
def test_format_price(tree: Tree, expected_result: str):
    assert format_price(tree) == expected_result


@pytest.mark.parametrize(
    "tree, expected_result",
    [
        (
            Tree(
                "per_unit_cost",
                [
                    Tree(
                        "amount",
                        [Token("SIGNED_NUMBER", "1234.56"), Token("CURRENCY", "USD")],
                    )
                ],
            ),
            "{ 1,234.56 USD }",
        ),
        (
            Tree(
                "total_cost",
                [
                    Tree(
                        "amount",
                        [Token("SIGNED_NUMBER", "1234.56"), Token("CURRENCY", "USD")],
                    )
                ],
            ),
            "{{ 1,234.56 USD }}",
        ),
        (
            Tree(
                "both_cost",
                [
                    Token("SIGNED_NUMBER", "789.01"),
                    Tree(
                        "amount",
                        [Token("SIGNED_NUMBER", "1234.56"), Token("CURRENCY", "USD")],
                    ),
                ],
            ),
            "{ 789.01 # 1,234.56 USD }",
        ),
        (
            Tree(
                "dated_cost",
                [
                    Tree(
                        "amount",
                        [Token("SIGNED_NUMBER", "1234.56"), Token("CURRENCY", "USD")],
                    ),
                    Token("DATE", "2022-04-01"),
                ],
            ),
            "{ 1,234.56 USD , 2022-04-01 }",
        ),
    ],
)
def test_format_cost(tree: Tree, expected_result: str):
    assert format_cost(tree) == expected_result
