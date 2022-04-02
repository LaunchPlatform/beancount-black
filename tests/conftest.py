import pathlib

import pytest

TEST_PACKAGE_FOLDER = pathlib.Path(__file__).parent
FIXTURE_FOLDER = TEST_PACKAGE_FOLDER / "fixtures"


@pytest.fixture
def fixtures_folder() -> pathlib.Path:
    return FIXTURE_FOLDER
