import io
import logging
import re
import typing

from lark import ParseTree
from lark import Token
from lark import Tree
from lark.visitors import Visitor


COMMENT_PREFIX = re.compile("[;*]+")


class StatementGroup(typing.NamedTuple):
    header: typing.Optional[Token]
    statements: typing.List[Tree]


class BeancountCollector(Visitor):
    def __init__(self, logger=None):
        super().__init__()
        self.logger = logger or logging.getLogger(__name__)
        # Collection of the header comments
        self.header_comments: typing.List[Token] = []
        self.statement_groups: typing.List[StatementGroup] = []

    def start(self, tree: Tree):
        for child in tree.children:
            self.visit_topdown(child)

    def statement(self, tree: Tree):
        first_child = tree.children[0]
        if isinstance(first_child, Token):
            # Comment only line
            if first_child.type == "COMMENT":
                self.comment_token(first_child)
            else:
                raise ValueError("Unexpected token type %s", first_child.type)
        else:
            if not self.statement_groups:
                self.statement_groups.append(StatementGroup(header=None, statements=[]))
            self.statement_groups[-1].statements.append(tree)

    def comment_token(self, token: Token):
        value = token.value.strip()
        if value.startswith("*"):
            self.logger.debug(
                "New statement group for %r at line %s", token.value, token.line
            )
            self.statement_groups.append(StatementGroup(header=token, statements=[]))
            return
        if token.line != len(self.header_comments) + 1:
            return
        if not self.statement_groups:
            self.logger.debug("Collect header comment %s at line %s", token, token.line)
            self.header_comments.append(token)


def format_comment(token: Token) -> str:
    value = token.value.strip()
    match = COMMENT_PREFIX.match(value)
    prefix = match.group(0)
    remain = value[len(prefix) :].strip()
    if not remain:
        return prefix
    return f"{prefix} {remain}"


def format_beancount(tree: ParseTree, output_file: io.TextIOBase):
    if tree.data != "start":
        raise ValueError("expected start as the root rule")
    collector = BeancountCollector()
    collector.visit_topdown(tree)

    # write header comments
    for header_comment in collector.header_comments:
        output_file.write(format_comment(header_comment) + "\n")
    if collector.header_comments and collector.statement_groups:
        output_file.write("\n")
