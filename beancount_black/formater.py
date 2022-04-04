import collections
import decimal
import enum
import io
import logging
import re
import typing

from lark import ParseTree
from lark import Token
from lark import Tree


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
    org_anchor: typing.Optional[Token]
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


class BeancountCollector:
    def __init__(self, logger=None):
        super().__init__()
        self.logger = logger or logging.getLogger(__name__)
        # Collection of the header comments
        self.header_comments: typing.List[Token] = []
        self.statement_groups: typing.List[StatementGroup] = []

    def collect(self, tree: Tree):
        if tree.data != "start":
            raise ValueError("Expected start")
        for child in tree.children:
            if child is None:
                continue
            self.statement(child)

    def statement(self, tree: Tree):
        if tree.data != "statement":
            raise ValueError("Expected statement")
        first_child = tree.children[0]
        if isinstance(first_child, Token):
            # Comment only line
            if first_child.type == "COMMENT":
                self.comment_token(first_child)
            elif first_child.type == "ORG_ANCHOR":
                self.org_anchor_token(first_child)
            else:
                raise ValueError("Unexpected token type %s", first_child.type)
        else:
            if not self.statement_groups:
                self.statement_groups.append(
                    StatementGroup(org_anchor=None, statements=[])
                )
            self.statement_groups[-1].statements.append(tree)

    def org_anchor_token(self, token: Token):
        self.logger.debug(
            "New statement group for %r at line %s", token.value, token.line
        )
        self.statement_groups.append(StatementGroup(org_anchor=token, statements=[]))

    def comment_token(self, token: Token):
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


def format_number(token: Token) -> str:
    value = token.value.replace(",", "")
    number = decimal.Decimal(value)
    # TODO: add width option
    return f"{number:,}"


def get_amount_columns(tree: Tree) -> typing.List[str]:
    if tree.data != "amount":
        raise ValueError("Expected a amount")
    number, currency = tree.children
    return [format_number(number), currency.value]


def get_directive_child_columns(child: typing.Union[Token, Tree]) -> typing.List[str]:
    if isinstance(child, Token):
        # TODO: some token may need reformat?
        return [child.value]
    tree: Tree = child
    if tree.data == "currencies":
        return [",".join(currency.value for currency in tree.children)]
    elif tree.data == "amount":
        return get_amount_columns(tree)
    raise ValueError(f"Unknown tree type {tree.data}")


def format_metadata_item(tree: Tree) -> str:
    if tree.data != "metadata_item":
        raise ValueError("Expected a metadata item")
    key_token, value_token = tree.children
    return f"{key_token.value}: {value_token.value}"


def format_date_directive(
    tree: Tree,
    column_widths: typing.Optional[typing.Dict[str, typing.Dict[int, str]]] = None,
) -> str:
    if tree.data != "date_directive":
        raise ValueError("Expected a date directive")
    if column_widths is None:
        column_widths = {}
    first_child = tree.children[0]
    date = first_child.children[0].value
    directive_type = first_child.data.value
    if directive_type == "txn":
        columns: typing.List[str] = [date]
        flag, payee, narration, annotations = first_child.children[1:]
        if flag is not None:
            columns.append(flag.value)
        if payee is not None:
            columns.append(payee.value)
        if narration is not None:
            columns.append(narration.value)
        if annotations is not None:
            annotation_values = [
                annotation.value for annotation in annotations.children
            ]
            links = list(filter(lambda v: v.startswith("^"), annotation_values))
            links.sort()
            hashes = list(filter(lambda v: v.startswith("#"), annotation_values))
            hashes.sort()
            columns.extend(links)
            columns.extend(hashes)
        return " ".join(columns)
    else:
        columns: typing.List[str] = [date, directive_type]
        for child in first_child.children[1:]:
            if child is None:
                continue
            columns.extend(get_directive_child_columns(child))
        directive_column_width = column_widths.get(directive_type)
        if directive_column_width is not None:
            for index, column in enumerate(columns):
                width = directive_column_width.get(index)
                if width is None:
                    continue
                new_value = f"{column:{width}}"
                columns[index] = new_value
        return " ".join(columns)


def format_posting(
    tree: Tree,
    account_width: str = "40",
    number_width: str = ">16",
) -> str:
    if tree.data != "posting":
        raise ValueError("Expected a posting")
    # Simple posting
    flag: Token
    account: Token
    amount: typing.Optional[Tree] = None
    cost: typing.Optional[Tree] = None
    tx_price: typing.Optional[Tree] = None
    if tree.children[0].data == "detailed_posting":
        flag, account, amount, cost, tx_price = tree.children[0].children
    else:
        flag, account = tree.children[0].children
    items: typing.List[str] = []
    if flag is not None:
        items.append(flag.value)
    # TODO: apply width here
    account_value = account.value
    if amount is not None:
        # only need to apply width when it's not short posting format
        account_value = f"{account_value:{account_width}}"
    items.append(account_value)
    # TODO: also apply width here
    if amount is not None:
        number, currency = get_amount_columns(amount)
        items.append(f"{number:{number_width}}")
        items.append(currency)
    # TODO: other parts
    return " ".join(items)


def format_metadata_lines(metadata_list: typing.List[Metadata]) -> typing.List[str]:
    lines: typing.List[str] = []
    for metadata in metadata_list:
        for comment in metadata.comments:
            lines.append(format_comment(comment))
        line = format_metadata_item(metadata.statement.children[0])
        tail_comment = metadata.statement.children[1]
        if tail_comment is not None:
            line += " " + format_comment(tail_comment)
        lines.append(line)
    return lines


def format_posting_lines(
    postings: typing.List[Posting], indent_width: int = 2
) -> typing.List[str]:
    lines: typing.List[str] = []
    for posting in postings:
        for comment in posting.comments:
            lines.append(format_comment(comment))
        line = format_posting(posting.statement.children[0])
        tail_comment = posting.statement.children[1]
        if tail_comment is not None:
            line += " " + format_comment(tail_comment)
        lines.append(line)
        metadata_lines = format_metadata_lines(posting.metadata)
        for metadata_line in metadata_lines:
            lines.append(" " * indent_width + metadata_line)
    return lines


def format_entry(entry: Entry, indent_width: int = 2) -> str:
    lines = []
    for comment in entry.comments:
        lines.append(format_comment(comment))

    if entry.type != EntryType.COMMENTS:
        first_child = entry.statement.children[0]
        if first_child.data == "date_directive":
            line = format_date_directive(first_child)
            tail_comment = entry.statement.children[1]
            if tail_comment is not None:
                line += " " + format_comment(tail_comment)
            lines.append(line)
            metadata_lines = format_metadata_lines(entry.metadata)
            for metadata_line in metadata_lines:
                lines.append(" " * indent_width + metadata_line)
            posting_lines = format_posting_lines(entry.postings)
            for posting_line in posting_lines:
                lines.append(" " * indent_width + posting_line)
        else:
            # TODO:
            pass
    return "\n".join(lines)


def format_statement_group(group: StatementGroup) -> str:
    lines: typing.List[str] = []
    if group.org_anchor is not None:
        lines.append(format_comment(group.org_anchor))
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
                raise ValueError(f"Unexpected token {first_child.type}")
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
        if not entry_group:
            continue
        for entry in entry_group:
            # TODO: pass along with column width
            lines.append(format_entry(entry))
        lines.append("")

    remain_entries = entry_groups.get(None, [])
    # TODO: sort remain entries
    for entry in remain_entries:
        lines.append(format_entry(entry))
    if remain_entries:
        lines.append("")

    print(entries)
    return "\n".join(lines)


def format_beancount(tree: ParseTree, output_file: io.TextIOBase):
    if tree.data != "start":
        raise ValueError("expected start as the root rule")
    collector = BeancountCollector()
    collector.collect(tree)

    # write header comments
    for header_comment in collector.header_comments:
        output_file.write(format_comment(header_comment) + "\n")
    if collector.header_comments and collector.statement_groups:
        output_file.write("\n")

    for group in collector.statement_groups:
        output_file.write(format_statement_group(group) + "\n")
