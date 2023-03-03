import collections
import datetime
import decimal
import enum
import io
import logging
import re
import typing

from lark import ParseTree
from lark import Token
from lark import Tree

VERBOSE_LOG_LEVEL = logging.NOTSET + 1

COMMENT_PREFIX = re.compile("[;*]+")
DEFAULT_INDENT_WIDTH = 2
DEFAULT_ACCOUNT_WIDTH = 30
DEFAULT_NUMBER_WIDTH = 12
# the difference of column width we need to make up for balance account field,
# so a balance statement starts with
#
#   "2022-01-01 balance "
#
BALANCE_PREFIX_WIDTH = 19


@enum.unique
class EntryType(enum.Enum):
    # Date directives
    OPEN = "OPEN"
    CLOSE = "CLOSE"
    BALANCE = "BALANCE"
    EVENT = "EVENT"
    COMMODITY = "COMMODITY"
    DOCUMENT = "DOCUMENT"
    PRICE = "PRICE"
    NOTE = "NOTE"
    PAD = "PAD"
    CUSTOM = "CUSTOM"
    TXN = "TXN"
    # Simple directives
    OPTION = "OPTION"
    INCLUDE = "INCLUDE"
    PLUGIN = "PLUGIN"
    # Other
    COMMENTS = "COMMENTS"


# The entries which are going to be listed in groups before all other entries
LEADING_ENTRY_TYPES: typing.List[EntryType] = [
    EntryType.COMMENTS,
    EntryType.INCLUDE,
    EntryType.PLUGIN,
    EntryType.OPTION,
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
    "price": EntryType.PRICE,
    "note": EntryType.NOTE,
    "pad": EntryType.PAD,
    "custom": EntryType.CUSTOM,
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
        return DATE_DIRECTIVE_ENTRY_TYPES[first_child.children[0].data.value]
    elif first_child.data == "simple_directive":
        return SIMPLE_DIRECTIVE_ENTRY_TYPES[first_child.children[0].data.value]
    else:
        raise ValueError(f"Unexpected first child type {first_child.data}")


class StatementGroup(typing.NamedTuple):
    section_header: typing.Optional[Token]
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


def parse_date(date_str: str) -> datetime.date:
    parts = date_str.split("-")
    return datetime.date(*(map(int, parts)))


class Collector:
    def __init__(self, logger: typing.Optional[logging.Logger] = None):
        super().__init__()
        self.logger = logger or logging.getLogger(__name__)
        # Collection of the header comments
        self.header_comments: typing.List[Token] = []
        self.statement_groups: typing.List[StatementGroup] = []

    def collect(self, tree: Tree):
        self.logger.info("Collecting")
        if tree.data != "start":
            raise ValueError("Expected start")
        for child in tree.children:
            if child is None:
                continue
            self.statement(child)

    def statement(self, tree: Tree):
        if tree.data != "statement":
            raise ValueError("Expected statement")
        self.logger.debug("Collecting statement at line %s", tree.meta.line)
        first_child = tree.children[0]
        if isinstance(first_child, Token):
            # Comment only line
            if first_child.type == "COMMENT":
                if self.comment_token(first_child):
                    # already added as part of the header comments, just return
                    return
            elif first_child.type == "SECTION_HEADER":
                self.section_header_token(first_child)
                return
            else:
                raise ValueError("Unexpected token type %s", first_child.type)
        if not self.statement_groups:
            self.statement_groups.append(
                StatementGroup(section_header=None, statements=[])
            )
        self.statement_groups[-1].statements.append(tree)

    def section_header_token(self, token: Token):
        self.logger.debug(
            "New statement group for %r at line %s", token.value, token.line
        )
        self.statement_groups.append(
            StatementGroup(section_header=token, statements=[])
        )

    def comment_token(self, token: Token) -> bool:
        if token.line != len(self.header_comments) + 1:
            return False
        if self.statement_groups:
            return False
        self.logger.debug("Collect header comment %s at line %s", token, token.line)
        self.header_comments.append(token)
        return True


class Formatter:
    def __init__(
        self,
        indent_width: int = DEFAULT_INDENT_WIDTH,
        min_account_width: int = DEFAULT_ACCOUNT_WIDTH,
        min_number_width: int = DEFAULT_NUMBER_WIDTH,
        logger: typing.Optional[logging.Logger] = None,
    ):
        self.indent_width = indent_width
        self.account_width = min_account_width
        self.number_width = min_number_width
        self.logger = logger or logging.getLogger(__name__)

    def get_entry_sorting_key(self, entry: Entry) -> typing.Tuple:
        first_child = entry.statement.children[0]
        if first_child.data == "date_directive":
            date = parse_date(first_child.children[0].children[0].value)
            return (date, entry.statement.meta.line)
        elif first_child.data == "simple_directive":
            # all simple directive child should be token, so just return them as tuple
            return tuple(
                child.value
                for child in first_child.children[0].children
                if child is not None
            )
        raise ValueError()

    def format_comment(self, token: Token) -> str:
        value = token.value.strip()
        match = COMMENT_PREFIX.match(value)
        prefix = match.group(0)
        remain = value[len(prefix) :].strip()
        if not remain:
            return prefix
        return f"{prefix} {remain}"

    def format_number(self, token: Token) -> str:
        if token.type != "NUMBER":
            raise ValueError("Expected a NUMBER")
        value = token.value.replace(",", "")
        number = decimal.Decimal(value)
        return f"{number:,}"

    def format_number_atom(self, tree_or_token: typing.Union[Tree, Token]) -> str:
        if isinstance(tree_or_token, Token):
            token: Token = tree_or_token
            if token.type == "NUMBER":
                return self.format_number(token)
            else:
                raise ValueError(f"Unknown token type {token.type}")
        elif isinstance(tree_or_token, Tree):
            tree: Tree = tree_or_token
            if tree.data == "number_atom":
                unary_op, number_atom = tree.children
                if unary_op.type != "UNARY_OP":
                    raise ValueError(f"Expected to be UNARY_OP but got {unary_op.data}")
                return unary_op.value + self.format_number_atom(number_atom)
            elif tree.data == "number_mul_expr":
                return self.format_number_mul_expr(tree)
            elif tree.data == "number_add_expr":
                return self.format_number_add_expr(tree)
            else:
                raise ValueError(f"Unknown tree {tree.data}")
        else:
            raise ValueError(f"Unexpected type {type(tree_or_token)}")

    def format_number_mul_expr(self, tree: Tree) -> str:
        if tree.data != "number_mul_expr":
            raise ValueError("Expected a number_mul_expr")
        items: typing.List[str] = []
        for child in tree.children:
            if isinstance(child, Token):
                if child.type == "MUL_OP":
                    items.append(f" {child.value} ")
                else:
                    items.append(self.format_number_atom(child))
            else:
                items.append(self.format_number_atom(child))
        return f'({"".join(items)})'

    def format_number_add_expr(self, tree: Tree) -> str:
        if tree.data != "number_add_expr":
            raise ValueError("Expected a number_add_expr")
        items: typing.List[str] = []
        for child in tree.children:
            if isinstance(child, Token):
                if child.type == "ADD_OP":
                    items.append(f" {child.value} ")
                else:
                    items.append(self.format_number_atom(child))
            elif isinstance(child, Tree) and child.data == "number_atom":
                items.append(self.format_number_atom(child))
            else:
                items.append(self.format_number_mul_expr(child))
        return f'({"".join(items)})'

    def format_number_expr(self, tree: Tree) -> str:
        if tree.data != "number_expr":
            raise ValueError("Expected a number_expr")
        first_child: typing.Union[Tree, Token] = tree.children[0]
        if isinstance(first_child, Tree) and first_child.data == "number_add_expr":
            return self.format_number_add_expr(first_child)
        return self.format_number_atom(first_child)

    def get_amount_columns(self, tree: Tree) -> typing.List[str]:
        if tree.data != "amount":
            raise ValueError("Expected a amount")
        number, currency = tree.children
        return [self.format_number_expr(number), currency.value]

    def format_price(self, tree: Tree) -> str:
        if tree.data not in {"per_unit_price", "total_price"}:
            raise ValueError("Expected a per_unit_price or total_price")
        amount = tree.children[0]
        amount_value = " ".join(self.get_amount_columns(amount))
        if tree.data == "per_unit_price":
            prefix = "@"
        elif tree.data == "total_price":
            prefix = "@@"
        else:
            raise ValueError()
        return " ".join([prefix, amount_value])

    def format_cost(self, tree: Tree) -> str:
        if tree.data not in {"per_unit_cost", "total_cost", "both_cost", "dated_cost"}:
            raise ValueError(
                "Expected a per_unit_cost, total_cost, both_cost or dated_cost"
            )
        if tree.data != "total_cost":
            bracket_start = "{"
            bracket_end = "}"
        else:
            bracket_start = "{{"
            bracket_end = "}}"
        items: typing.List[str] = []
        if tree.data in {"per_unit_cost", "total_cost", "dated_cost"}:
            amount = tree.children[0]
            amount_value = " ".join(self.get_amount_columns(amount))
            items.append(amount_value)
        if tree.data == "both_cost":
            number, amount = tree.children
            number_value = self.format_number_expr(number)
            amount_value = " ".join(self.get_amount_columns(amount))
            items.append(number_value)
            items.append("#")
            items.append(amount_value)
        elif tree.data == "dated_cost":
            date = tree.children[1]
            items[-1] += ","
            items.append(date.value)
        return bracket_start + " ".join(items) + bracket_end

    def get_directive_child_columns(
        self, child: typing.Union[Token, Tree]
    ) -> typing.List[str]:
        if isinstance(child, Token):
            # TODO: some token may need reformat?
            return [child.value]
        tree: Tree = child
        if tree.data == "currencies":
            return [",".join(currency.value for currency in tree.children)]
        elif tree.data == "amount":
            return self.get_amount_columns(tree)
        elif tree.data == "number_expr":
            return [self.format_number_expr(tree)]
        raise ValueError(f"Unknown tree type {tree.data}")

    def format_metadata_item(self, tree: Tree) -> str:
        if tree.data != "metadata_item":
            raise ValueError("Expected a metadata item")
        key_token, value_token = tree.children
        return f"{key_token.value}: {value_token.value}"

    def format_simple_directive(self, tree: Tree) -> str:
        if tree.data != "simple_directive":
            raise ValueError("Expected a simple directive")
        first_child = tree.children[0]
        items: typing.List[str] = [first_child.data.value] + [
            child.value for child in first_child.children if child is not None
        ]
        return " ".join(items)

    def format_date_directive(self, tree: Tree) -> str:
        if tree.data != "date_directive":
            raise ValueError("Expected a date directive")
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
                columns.extend(self.get_directive_child_columns(child))
            if directive_type == "balance":
                for index, column in enumerate(columns):
                    prefix = ""
                    # account
                    if index == 2:
                        width = self.account_width
                    # number
                    elif index == 3:
                        width = self.number_width
                        prefix = ">"
                    else:
                        continue
                    new_value = f"{column:{prefix}{width}}"
                    columns[index] = new_value
            return " ".join(columns)

    def format_posting(self, tree: Tree) -> str:
        if tree.data != "posting":
            raise ValueError("Expected a posting")
        # Simple posting
        flag: Token
        account: Token
        amount: typing.Optional[Tree] = None
        cost: typing.Optional[Tree] = None
        price: typing.Optional[Tree] = None
        if tree.children[0].data == "detailed_posting":
            flag, account, amount, cost, price = tree.children[0].children
        else:
            flag, account = tree.children[0].children
        items: typing.List[str] = []
        if flag is not None:
            items.append(flag.value)
        account_value = account.value
        # only need to apply width when it's not short posting format
        if amount is not None:
            # Need to add the difference for balance prefix width
            width = self.account_width + (BALANCE_PREFIX_WIDTH - self.indent_width)
            account_value = f"{account_value:{width}}"
        items.append(account_value)
        if amount is not None:
            number, currency = self.get_amount_columns(amount)
            items.append(f"{number:>{self.number_width}}")
            items.append(currency)
        if cost is not None:
            items.append(self.format_cost(cost))
        if price is not None:
            items.append(self.format_price(price))
        return " ".join(items)

    def format_metadata_lines(
        self, metadata_list: typing.List[Metadata]
    ) -> typing.List[str]:
        lines: typing.List[str] = []
        for metadata in metadata_list:
            for comment in metadata.comments:
                lines.append(self.format_comment(comment))
            line = self.format_metadata_item(metadata.statement.children[0])
            tail_comment = metadata.statement.children[1]
            if tail_comment is not None:
                line += " " + self.format_comment(tail_comment)
            lines.append(line)
        return lines

    def format_posting_lines(
        self,
        postings: typing.List[Posting],
    ) -> typing.List[str]:
        lines: typing.List[str] = []
        for posting in postings:
            for comment in posting.comments:
                lines.append(self.format_comment(comment))
            line = self.format_posting(posting.statement.children[0])
            tail_comment = posting.statement.children[1]
            if tail_comment is not None:
                line += " " + self.format_comment(tail_comment)
            lines.append(line)
            metadata_lines = self.format_metadata_lines(posting.metadata)
            for metadata_line in metadata_lines:
                lines.append(" " * self.indent_width + metadata_line)
        return lines

    def format_entry(self, entry: Entry) -> str:
        self.logger.debug(
            "Format entry type %s at line %s",
            entry.type.value,
            entry.statement.meta.line,
        )
        self.logger.log(VERBOSE_LOG_LEVEL, "Entry value %s", entry)
        lines = []
        for comment in entry.comments:
            lines.append(self.format_comment(comment))

        if entry.type != EntryType.COMMENTS:
            first_child = entry.statement.children[0]
            if first_child.data == "date_directive":
                line = self.format_date_directive(first_child)
                tail_comment = entry.statement.children[1]
                if tail_comment is not None:
                    line += " " + self.format_comment(tail_comment)
                lines.append(line)
                metadata_lines = self.format_metadata_lines(entry.metadata)
                for metadata_line in metadata_lines:
                    lines.append(" " * self.indent_width + metadata_line)
                posting_lines = self.format_posting_lines(entry.postings)
                for posting_line in posting_lines:
                    lines.append(" " * self.indent_width + posting_line)
            else:
                line = self.format_simple_directive(first_child)
                tail_comment = entry.statement.children[1]
                if tail_comment is not None:
                    line += " " + self.format_comment(tail_comment)
                lines.append(line)
        return "\n".join(lines)

    def format_statement_group(self, group: StatementGroup) -> str:
        sections: typing.List[str] = []
        if group.section_header is not None:
            sections.append(self.format_comment(group.section_header))

        entries: typing.List[Entry] = []
        comments: typing.List[Token] = []
        for statement in group.statements:
            first_child = statement.children[0]
            if isinstance(first_child, Token):
                if first_child.type == "COMMENT":
                    comments.append(first_child)
                else:
                    raise ValueError(f"Unexpected token {first_child.type}")
            else:
                if comments and comments[-1].line + 1 != statement.meta.line:
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
                    comments = []
                    continue
                elif first_child.data == "metadata_item":
                    last_entry = entries[-1]
                    metadata = Metadata(comments=comments, statement=statement)
                    if last_entry.postings:
                        last_posting: Posting = last_entry.postings[-1]
                        last_posting.metadata.append(metadata)
                    else:
                        last_entry.metadata.append(metadata)
                    comments = []
                    continue
                entry = Entry(
                    type=get_entry_type(statement),
                    comments=comments,
                    statement=statement,
                    metadata=[],
                    postings=[],
                )
                entries.append(entry)
                comments = []

        if comments:
            entry = Entry(
                type=EntryType.COMMENTS,
                comments=comments,
                # TODO: maybe pass None makes more sense here?
                statement=statement,
                metadata=[],
                postings=[],
            )
            entries.append(entry)
            comments = []
            # TODO: or add to tail comments?

        # breaking down entries into groups by leading entry type, comments or
        # None (means doesn't belong to the leading groups or comments)
        entry_groups: typing.Dict[
            typing.Optional[EntryType], typing.List[Entry]
        ] = collections.defaultdict(list)
        for entry in entries:
            entry_type: typing.Optional[EntryType] = None
            if entry.type in LEADING_ENTRY_TYPES:
                entry_type = entry.type
            entry_groups[entry_type].append(entry)

        for entry_type in LEADING_ENTRY_TYPES:
            lines: typing.List[str] = []
            entry_group = entry_groups.get(entry_type, [])
            if not entry_group:
                continue
            entry_group.sort(key=self.get_entry_sorting_key)
            for entry in entry_group:
                lines.append(self.format_entry(entry))
            if lines:
                sections.append("\n".join(lines))

        remain_entries = entry_groups.get(None, [])
        remain_entries.sort(key=self.get_entry_sorting_key)
        for entry in remain_entries:
            sections.append(self.format_entry(entry))

        return "\n\n".join(sections)

    def calculate_column_widths(self, tree: ParseTree):
        self.logger.info("Calculate column width")
        for statement in tree.children:
            if statement is None:
                continue
            self.logger.debug(
                "Calculate column width for statement at line %s", statement.meta.line
            )
            self.logger.log(VERBOSE_LOG_LEVEL, "Statement %s", statement)
            first_child = statement.children[0]
            if isinstance(first_child, Token):
                continue
            account: typing.Optional[Token] = None
            amount: typing.Optional[Tree] = None
            if first_child.data == "posting":
                # Simple posting
                if first_child.children[0].data == "detailed_posting":
                    _, account, amount, *_ = first_child.children[0].children
                else:
                    _, account = first_child.children[0].children
            elif first_child.data == "date_directive":
                if first_child.children[0].data == "balance":
                    _, account, amount = first_child.children[0].children
            balance_account_column_diff = BALANCE_PREFIX_WIDTH - self.indent_width
            if account is not None and len(account.value) > self.account_width:
                # bump account width
                self.account_width = len(account.value)
            if amount is not None:
                width = len(self.format_number_expr(amount.children[0]))
                if width > self.number_width:
                    # bump number width
                    self.number_width = width

    def format(self, tree: ParseTree, output_file: io.TextIOBase):
        if tree.data != "start":
            raise ValueError("expected start as the root rule")
        self.calculate_column_widths(tree)

        collector = Collector()
        collector.collect(tree)

        # write header comments
        sections: typing.List[str] = []
        if collector.header_comments:
            lines: typing.List[str] = [
                self.format_comment(header_comment)
                for header_comment in collector.header_comments
            ]
            sections.append("\n".join(lines))

        for group in collector.statement_groups:
            sections.append(self.format_statement_group(group))

        output_file.write("\n\n".join(sections))
        if sections:
            output_file.write("\n")
