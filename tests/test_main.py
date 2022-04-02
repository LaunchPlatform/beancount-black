import pathlib
import shutil

import pytest
from click.testing import CliRunner

from beancount_black.main import main


@pytest.mark.parametrize(
    "input_file, expected_output_file",
    [
        ("simple.bean", "simple.bean"),
    ],
)
def test_main(
    tmp_path: pathlib.Path,
    fixtures_folder: pathlib.Path,
    input_file: pathlib.Path,
    expected_output_file: pathlib.Path,
):
    input_file_path = fixtures_folder / "input" / input_file
    expected_output_file_path = fixtures_folder / "expected_output" / input_file
    tmp_input_file = tmp_path / "input.bean"
    shutil.copy2(input_file_path, tmp_input_file)
    runner = CliRunner()
    result = runner.invoke(main, [str(tmp_input_file)])
    assert result.exit_code == 0
    assert result.output == ""