import logging
import tempfile
import typing

import click
from beancount_parser.parser import make_parser

from .formater import format


@click.command()
@click.argument("filename", nargs=-1)
def main(filename: typing.List[str]):
    logger = logging.getLogger(__name__)
    parser = make_parser()
    for name in filename:
        logger.info("Processing file %s", name)
        with open(name, "rt") as input_file:
            tree = parser.parse(input_file)
        with tempfile.NamedTemporaryFile(mode="wt", suffix=".bean") as output_file:
            format(tree, output_file)
        # TODO: swap the file and remove old file
        # TODO: make a backup if the file content changes


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
