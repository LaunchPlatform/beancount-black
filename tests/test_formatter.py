import typing

import pytest
from beancount_parser.parser import make_parser
from lark import Token
from lark import Tree

from beancount_black.formatter import Formatter


@pytest.fixture
def formatter() -> Formatter:
    return Formatter()


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
def test_format_comment(formatter: Formatter, value: str, expected_result: str):
    token = Token("COMMENT", value=value)
    assert formatter.format_comment(token) == expected_result


@pytest.mark.parametrize(
    "value, expected_result",
    [
        ("+123.4567", "123.4567"),
        ("-123.4567", "-123.4567"),
        ("1234567.90", "1,234,567.90"),
    ],
)
def test_format_number(formatter: Formatter, value: str, expected_result: str):
    token = Token("SIGNED_NUMBER", value=value)
    assert formatter.format_number(token) == expected_result


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
            dict(account_width=20, number_width=10),
            "1970-01-01  balance     Assets:Bank  12.34    USD",
            "1970-01-01 balance Assets:Bank               12.34 USD",
        ),
    ],
)
def test_format_date_directive(
    formatter: Formatter,
    column_widths: typing.Optional[typing.Dict],
    text: str,
    expected_result: str,
):
    parser = make_parser()
    root = parser.parse(text)
    date_directive = root.children[0]
    if column_widths is not None:
        for key, value in column_widths.items():
            setattr(formatter, key, value)
    assert formatter.format_date_directive(date_directive) == expected_result


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
def test_format_price(formatter: Formatter, tree: Tree, expected_result: str):
    assert formatter.format_price(tree) == expected_result


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
def test_format_cost(formatter: Formatter, tree: Tree, expected_result: str):
    assert formatter.format_cost(tree) == expected_result
