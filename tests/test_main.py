import pathlib
import shutil

import pytest
from click.testing import CliRunner

from beancount_black.main import create_backup
from beancount_black.main import main


def test_create_backup(tmp_path: pathlib.Path):
    content = "; my book\n; foobar"
    input_file = tmp_path / "input.bean"
    input_file.write_text(content)
    create_backup(input_file, suffix=".backup")
    backup_file = tmp_path / "input.bean.backup"
    assert backup_file.read_text() == content


def test_create_backup_with_conflicts(tmp_path: pathlib.Path):
    for i in range(5):
        input_file = tmp_path / "input.bean"
        input_file.write_text(str(i))
        create_backup(input_file, suffix=".backup")
    backup_file = tmp_path / "input.bean.backup"
    assert backup_file.read_text() == "0"
    for i in range(1, 4):
        backup_file = tmp_path / f"input.bean.backup.{i}"
        assert backup_file.read_text() == str(i)


@pytest.mark.parametrize(
    "input_file, expected_output_file",
    [
        ("simple.bean", "simple.bean"),
        ("cost_and_price.bean", "cost_and_price.bean"),
        ("header_comments.bean", "header_comments.bean"),
        ("sections.bean", "sections.bean"),
        ("column_width.bean", "column_width.bean"),
        ("txn.bean", "txn.bean"),
        ("number_expr.bean", "number_expr.bean"),
    ],
)
@pytest.mark.parametrize("stdin_mode", [False, True])
def test_main(
    tmp_path: pathlib.Path,
    fixtures_folder: pathlib.Path,
    input_file: pathlib.Path,
    expected_output_file: pathlib.Path,
    stdin_mode: bool,
):
    input_file_path = fixtures_folder / "input" / input_file
    expected_output_file_path = fixtures_folder / "expected_output" / input_file
    tmp_input_file = tmp_path / "input.bean"
    shutil.copy2(input_file_path, tmp_input_file)
    runner = CliRunner()
    if stdin_mode:
        result = runner.invoke(
            main, ["-s", "-"], input=tmp_input_file.read_text(), catch_exceptions=False
        )
    else:
        result = runner.invoke(main, [str(tmp_input_file)], catch_exceptions=False)
    assert result.exit_code == 0
    if stdin_mode:
        updated_input_content = result.stdout
    else:
        updated_input_content = tmp_input_file.read_text()
    expected_output_content = expected_output_file_path.read_text()
    assert updated_input_content == expected_output_content
