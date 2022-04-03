import pytest
from lark import Token

from beancount_black.formater import format_comment


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
