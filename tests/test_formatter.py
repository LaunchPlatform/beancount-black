import pytest
from beancount_parser.parser import make_parser
from lark import Token

from beancount_black.formater import format_comment
from beancount_black.formater import format_date_directive


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
    "text, expected_result",
    [
        (
            "1970-01-01  open     Assets:Bank",
            "1970-01-01 open Assets:Bank",
        ),
        (
            "1970-01-01  open     Assets:Bank   USD",
            "1970-01-01 open Assets:Bank USD",
        ),
        (
            "1970-01-01  open     Assets:Bank   USD,BTC",
            "1970-01-01 open Assets:Bank USD,BTC",
        ),
        (
            '1970-01-01  open     Assets:Bank   USD,BTC  "strict" ',
            '1970-01-01 open Assets:Bank USD,BTC "strict"',
        ),
    ],
)
def test_format_date_directive(text: str, expected_result: str):
    parser = make_parser()
    root = parser.parse(text)
    date_directive = root.children[0]
    assert format_date_directive(date_directive) == expected_result
