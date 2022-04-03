import collections
import enum
import io
import logging
import re
import typing

from lark import ParseTree
from lark import Token
from lark import Tree
from lark.visitors import Visitor


COMMENT_PREFIX = re.compile("[;*]+")


@enum.unique
class EntryType(enum.Enum):
    # Date directives
    OPEN = "OPEN"
    CLOSE = "CLOSE"
    BALANCE = "BALANCE"
    EVENT = "EVENT"
    COMMODITY = "COMMODITY"
    DOCUMENT = "DOCUMENT"
    NOTE = "NOTE"
    PAD = "PAD"
    TXN = "TXN"
    # Simple directives
    OPTION = "OPTION"
    INCLUDE = "INCLUDE"
    PLUGIN = "PLUGIN"
    # Other
    COMMENTS = "COMMENTS"


# The entries which are going to be listed in groups before all other entries
LEADING_ENTRY_TYPES: typing.List[EntryType] = [
    EntryType.INCLUDE,
    EntryType.OPTION,
    EntryType.PLUGIN,
    EntryType.COMMODITY,
    EntryType.OPEN,
    EntryType.CLOSE,
]

DATE_DIRECTIVE_ENTRY_TYPES = {
    "open": EntryType.OPEN,
    "close": EntryType.CLOSE,
    "balance": EntryType.BALANCE,
    "event": EntryType.EVENT,
    "commodity": EntryType.COMMODITY,
    "document": EntryType.DOCUMENT,
    "note": EntryType.NOTE,
    "pad": EntryType.PAD,
    "txn": EntryType.TXN,
}

SIMPLE_DIRECTIVE_ENTRY_TYPES = {
    "option": EntryType.OPTION,
    "include": EntryType.INCLUDE,
    "plugin": EntryType.PLUGIN,
}


def get_entry_type(statement: Tree) -> EntryType:
    first_child: Tree = statement.children[0]
    if first_child.data == "date_directive":
        return DATE_DIRECTIVE_ENTRY_TYPES[first_child.children[0].data]
    elif first_child.data == "simple_directive":
        return SIMPLE_DIRECTIVE_ENTRY_TYPES[first_child.children[0].data]
    else:
        raise ValueError(f"Unexpected first child type {first_child.data}")


class StatementGroup(typing.NamedTuple):
    header: typing.Optional[Token]
    statements: typing.List[Tree]


class Metadata(typing.NamedTuple):
    comments: typing.List[Token]
    statement: Tree


class Posting(typing.NamedTuple):
    comments: typing.List[Token]
    statement: Tree
    metadata: typing.List[Metadata]


class Entry(typing.NamedTuple):
    type: EntryType
    comments: typing.List[Token]
    statement: Tree
    metadata: typing.List[Metadata]
    postings: typing.List[Posting]


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


def format_directive_child(child: typing.Union[Token, Tree]) -> str:
    if isinstance(child, Token):
        # TODO: some token may need reformat?
        return child.value
    tree: Tree = child
    if tree.data == "currencies":
        return ",".join(currency.value for currency in tree.children)
    raise ValueError(f"Unknown tree type {tree.data}")


def format_date_directive(tree: Tree) -> str:
    if tree.data != "date_directive":
        raise ValueError("Expected a date directive")
    first_child = tree.children[0]
    if first_child.data == "txn":
        return ""
    else:
        date = format_directive_child(first_child.children[0])
        items: typing.List[str] = [date, first_child.data]
        items.extend(
            map(
                format_directive_child,
                filter(lambda child: child is not None, first_child.children[1:]),
            )
        )
        return " ".join(items)


def format_entry(entry: Entry) -> str:
    lines = []
    for comment in entry.comments:
        lines.append(format_comment(comment))
    if entry.type != EntryType.COMMENTS:
        pass
    return "\n".join(lines)


def format_statement_group(group: StatementGroup) -> str:
    lines: typing.List[str] = []
    if group.header is not None:
        lines.append(format_comment(group.header))
        if group.statements:
            lines.append("")

    entries: typing.List[Entry] = []
    comments: typing.List[Token] = []
    for statement in group.statements:
        first_child = statement.children[0]
        if isinstance(first_child, Token):
            if first_child.type == "COMMENT":
                comments.append(statement)
            else:
                raise ValueError(f"Unepxected token {first_child.type}")
        else:
            if comments and comments[-1].line != statement.meta.line + 1:
                # Standalone comment group
                entry = Entry(
                    type=EntryType.COMMENTS,
                    comments=comments,
                    statement=statement,
                    metadata=[],
                    postings=[],
                )
                entries.append(entry)
                comments = []
            if first_child.data == "posting":
                last_entry = entries[-1]
                if last_entry.type != EntryType.TXN:
                    raise ValueError("Transaction expected")
                last_entry.postings.append(
                    Posting(comments=comments, statement=statement, metadata=[])
                )
                continue
            elif first_child.data == "metadata_item":
                last_entry = entries[-1]
                metadata = Metadata(comments=comments, statement=statement)
                if last_entry.postings:
                    last_posting: Posting = last_entry.postings[-1]
                    last_posting.metadata.append(metadata)
                else:
                    last_entry.metadata.append(metadata)
                continue
            entry = Entry(
                type=get_entry_type(statement),
                comments=comments,
                statement=statement,
                metadata=[],
                postings=[],
            )
            entries.append(entry)

    if comments:
        entry = Entry(
            type=EntryType.COMMENTS,
            comments=comments,
            statement=statement,
            metadata=[],
            postings=[],
        )
        entries.append(entry)
        # TODO: or add to tail comments?

    # breaking down entries into groups by leading entry type, comments or
    # None (means doesn't belong to the leading groups or comments)
    entry_groups: typing.Dict[
        typing.Optional[EntryType], typing.List[Entry]
    ] = collections.defaultdict(list)
    for entry in entries:
        entry_type: typing.Optional[EntryType] = None
        if entry.type in LEADING_ENTRY_TYPES or entry_type == EntryType.COMMENTS:
            entry_type = entry.type
        entry_groups[entry_type].append(entry)

    for comment_group in comments:
        # TODO: output comment group
        pass

    for entry_type in LEADING_ENTRY_TYPES:
        entry_group = entry_groups.get(entry_type, [])
        # TODO: sort entry group
        for entry in entry_group:
            pass
        if entry_group:
            lines.append("")

    print(entries)
    return "\n".join(lines)


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

    try:
        for group in collector.statement_groups:
            output_file.write(format_statement_group(group) + "\n")
    except Exception as e:
        print()
        pass
