import io
import logging
import typing

from lark import ParseTree
from lark import Token
from lark import Tree
from lark.visitors import Visitor


class BeancountCollector(Visitor):
    def __init__(self, logger=None):
        super().__init__()
        self.logger = logger or logging.getLogger(__name__)
        # Collection of the header comments
        self.header_comments: typing.List[Token] = []
        self.statements: typing.List[Tree] = []

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
            self.statements.append(tree)

    def comment_token(self, token: Token):
        value = token.value.strip()
        if value.startswith("*"):
            # We simply ignore star comments for now
            self.logger.warning("Ignore star comments at line %s", token.line)
            return
        if token.line != len(self.header_comments) + 1:
            return
        if not self.statements:
            self.logger.debug("Collect header comment %s at line %s", token, token.line)
            self.header_comments.append(token)


def format_comment(token: Token) -> str:
    # TODO: ensure the leading space after ';'
    return token.value.strip()


def format(tree: ParseTree, output_file: io.TextIOBase):
    if tree.data != "start":
        raise ValueError("expected start as the root rule")
    collector = BeancountCollector()
    collector.visit_topdown(tree)

    # write header comments
    for header_comment in collector.header_comments:
        # TODO: format comment, ensure leading space
        print(format_comment(header_comment), file=output_file)
    if collector.header_comments():
        print(file=output_file)
