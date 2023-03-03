import logging
import os
import pathlib
import shutil
import tempfile
import typing

import click
from beancount_parser.parser import make_parser

from .formatter import Formatter
from .formatter import VERBOSE_LOG_LEVEL


LOG_LEVEL_MAP = {
    "verbose": VERBOSE_LOG_LEVEL,
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "warning": logging.WARNING,
    "error": logging.ERROR,
    "fatal": logging.FATAL,
}


def create_backup(src: pathlib.Path, suffix: str) -> pathlib.Path:
    """Create a backup file

    :param src: path of source file to create backup
    :param suffix: suffix of backup file
    :return: the path of backup file
    """
    conflicts = 0
    while True:
        backup_path: pathlib.Path = src.with_name(src.name + suffix)
        if conflicts > 0:
            backup_path = backup_path.with_name(f"{backup_path.name}.{conflicts}")
        if backup_path.exists():
            conflicts += 1
            continue
        shutil.copy2(src, backup_path)
        return backup_path


@click.command()
@click.argument("filename", type=click.Path(exists=True, dir_okay=False), nargs=-1)
@click.option(
    "--backup-suffix", type=str, default=".backup", help="suffix of backup file"
)
@click.option(
    "-l",
    "--log-level",
    type=click.Choice(list(LOG_LEVEL_MAP), case_sensitive=False),
    default=lambda: os.environ.get("LOG_LEVEL", "INFO"),
)
@click.option("-n", "--no-backup", is_flag=True, help="Do not create backup file")
def main(
    filename: typing.List[click.Path],
    backup_suffix: str,
    log_level: str,
    no_backup: bool,
):
    logging.basicConfig(level=LOG_LEVEL_MAP[log_level])
    logger = logging.getLogger(__name__)
    parser = make_parser()
    formatter = Formatter()
    for name in filename:
        logger.info("Processing file %s", name)
        with open(name, "rt") as input_file:
            input_content = input_file.read()
            tree = parser.parse(input_content)
        with tempfile.NamedTemporaryFile(mode="wt+", suffix=".bean") as output_file:
            formatter.format(tree, output_file)
            output_file.seek(0)
            output_content = output_file.read()
            if input_content == output_content:
                logger.info("File %s is not changed, skip", name)
                continue
            if not no_backup:
                backup_path = create_backup(
                    src=pathlib.Path(str(name)), suffix=backup_suffix
                )
                logger.info("File %s changed, backup to %s", name, backup_path)
            output_file.seek(0)
            with open(name, "wt") as input_file:
                shutil.copyfileobj(output_file, input_file)
    logger.info("done")


if __name__ == "__main__":
    main()
