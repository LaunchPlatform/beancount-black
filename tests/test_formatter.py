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
    "tree, expected_result",
    [
        (
            Tree(
                "number_expr",
                [
                    Tree(
                        "number_mul_expr",
                        [
                            Tree(
                                "number_add_expr",
                                [
                                    Token("NUMBER", "1"),
                                    Token("ADD_OP", "+"),
                                    Token("NUMBER", "2"),
                                ],
                            ),
                            Token("MUL_OP", "*"),
                            Token("NUMBER", "3"),
                            Token("MUL_OP", "/"),
                            Tree(
                                "number_atom",
                                [Token("UNARY_OP", "-"), Token("NUMBER", "4")],
                            ),
                        ],
                    )
                ],
            ),
            "((1 + 2) * 3 / -4)",
        ),
        (
            Tree(
                "number_expr",
                [
                    Tree(
                        "number_atom",
                        [Token("UNARY_OP", "-"), Token("NUMBER", "123.4567")],
                    )
                ],
            ),
            "-123.4567",
        ),
        (
            Tree(
                "number_expr",
                [
                    Tree(
                        "number_atom",
                        [Token("UNARY_OP", "+"), Token("NUMBER", "123.4567")],
                    )
                ],
            ),
            "+123.4567",
        ),
        (Tree("number_expr", [Token("NUMBER", value="1234567.90")]), "1,234,567.90"),
        (Tree("number_expr", [Token("NUMBER", value="0.00000001")]), "0.00000001"),
    ],
)
def test_format_number_expr(formatter: Formatter, tree: Tree, expected_result: str):
    assert formatter.format_number_expr(tree) == expected_result


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
        (
            dict(account_width=20, number_width=10),
            "1970-01-01  balance     Assets:Bank  12.34 ~ 0.015   USD",
            "1970-01-01 balance Assets:Bank               12.34 ~ 0.015 USD",
        ),
        (
            dict(account_width=20, number_width=10),
            "1970-01-01  balance     Assets:Bank  0.00000001    USD",
            "1970-01-01 balance Assets:Bank          0.00000001 USD",
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
    date_directive = root.children[0].children[0]
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
                        [
                            Tree("number_expr", [Token("NUMBER", "1234.56")]),
                            Token("CURRENCY", "USD"),
                        ],
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
                        [
                            Tree("number_expr", [Token("NUMBER", "1234.56")]),
                            Token("CURRENCY", "USD"),
                        ],
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
                "cost_spec",
                [
                    Tree(
                        "cost_item",
                        [
                            Tree(
                                "amount",
                                [
                                    Tree(
                                        "number_expr",
                                        [
                                            Token(
                                                "NUMBER",
                                                "1,234.56",
                                            )
                                        ],
                                    ),
                                    Token("CURRENCY", "USD"),
                                ],
                            )
                        ],
                    )
                ],
            ),
            "{1,234.56 USD}",
        ),
        (
            Tree(
                "total_cost",
                [
                    Tree(
                        "amount",
                        [
                            Tree("number_expr", [Token("NUMBER", "1234.56")]),
                            Token("CURRENCY", "USD"),
                        ],
                    )
                ],
            ),
            "{{1,234.56 USD}}",
        ),
        (
            Tree(
                "both_cost",
                [
                    Tree("number_expr", [Token("NUMBER", "789.01")]),
                    Tree(
                        "amount",
                        [
                            Tree("number_expr", [Token("NUMBER", "1234.56")]),
                            Token("CURRENCY", "USD"),
                        ],
                    ),
                ],
            ),
            "{789.01 # 1,234.56 USD}",
        ),
        (
            Tree(
                "cost_spec",
                [
                    Tree(
                        "cost_item",
                        [
                            Tree(
                                "amount",
                                [
                                    Tree(
                                        "number_expr",
                                        [
                                            Token(
                                                "NUMBER",
                                                "1,234.56",
                                            )
                                        ],
                                    ),
                                    Token("CURRENCY", "USD"),
                                ],
                            )
                        ],
                    ),
                    Tree(
                        "cost_item",
                        [Token("DATE", "2022-04-01")],
                    ),
                ],
            ),
            "{1,234.56 USD, 2022-04-01}",
        ),
        (
            Tree(
                "cost_spec",
                [
                    Tree(
                        "cost_item",
                        [
                            Tree(
                                "amount",
                                [
                                    Tree(
                                        "number_expr",
                                        [
                                            Token(
                                                "NUMBER",
                                                "1,234.56",
                                            )
                                        ],
                                    ),
                                    Token("CURRENCY", "USD"),
                                ],
                            )
                        ],
                    ),
                    Tree(
                        "cost_item",
                        [Token("DATE", "2022-04-01")],
                    ),
                    Tree(
                        "cost_item",
                        [Token("ESCAPED_STRING", '"my-label"')],
                    ),
                ],
            ),
            '{1,234.56 USD, 2022-04-01, "my-label"}',
        ),
        (
            Tree(
                "cost_spec",
                [
                    Tree(
                        "cost_item",
                        [
                            Tree(
                                "amount",
                                [
                                    Tree(
                                        "number_expr",
                                        [
                                            Token(
                                                "NUMBER",
                                                "1,234.56",
                                            )
                                        ],
                                    ),
                                    Token("CURRENCY", "USD"),
                                ],
                            )
                        ],
                    ),
                    Tree(
                        "cost_item",
                        [Token("DATE", "2022-04-01")],
                    ),
                    Tree(
                        "cost_item",
                        [Token("ESCAPED_STRING", '"my-label"')],
                    ),
                    Tree(
                        "cost_item",
                        [Token("ASTERISK", "*")],
                    ),
                ],
            ),
            '{1,234.56 USD, 2022-04-01, "my-label", *}',
        ),
        (
            Tree(
                "cost_spec",
                [
                    Tree(
                        "cost_item",
                        [Token("ASTERISK", "*")],
                    )
                ],
            ),
            "{*}",
        ),
    ],
)
def test_format_cost(formatter: Formatter, tree: Tree, expected_result: str):
    assert formatter.format_cost(tree) == expected_result


@pytest.mark.parametrize(
    "tree, expected_result",
    [
        (
            Tree(
                Token("RULE", "metadata_item"),
                [
                    Token("METADATA_KEY", "total"),
                    Tree(Token("RULE", "number_expr"), [Token("NUMBER", "50000")]),
                ],
            ),
            "total: 50,000",
        ),
        (
            Tree(
                Token("RULE", "metadata_item"),
                [
                    Token("METADATA_KEY", "doc"),
                    Token("ESCAPED_STRING", '"/path/to/my-doc"'),
                ],
            ),
            'doc: "/path/to/my-doc"',
        ),
        (
            Tree(
                Token("RULE", "metadata_item"),
                [Token("METADATA_KEY", "account"), Token("ACCOUNT", "Assets:Cash")],
            ),
            "account: Assets:Cash",
        ),
        (
            Tree(
                Token("RULE", "metadata_item"),
                [Token("METADATA_KEY", "currency"), Token("CURRENCY", "USD")],
            ),
            "currency: USD",
        ),
        (
            Tree(
                Token("RULE", "metadata_item"),
                [Token("METADATA_KEY", "date"), Token("DATE", "2024-03-16")],
            ),
            "date: 2024-03-16",
        ),
        (
            Tree(
                Token("RULE", "metadata_item"),
                [Token("METADATA_KEY", "tags"), Token("TAGS", "#tags1 #tags2")],
            ),
            "tags: #tags1 #tags2",
        ),
    ],
)
def test_format_metadata_item(formatter: Formatter, tree: Tree, expected_result: str):
    assert formatter.format_metadata_item(tree) == expected_result
