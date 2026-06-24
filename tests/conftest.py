"""Shared fixtures for the test suite."""
import pytest
from pathlib import Path
from db import init_db, SecureDataAccess

TEST_DB = Path(__file__).parent.parent / "employees.db"
TEST_CSV = Path(__file__).parent.parent / "employees.csv"


@pytest.fixture(scope="session", autouse=True)
def db(tmp_path_factory):
    """Ensure the SQLite DB exists before any test runs."""
    if not TEST_DB.exists():
        init_db(TEST_CSV, TEST_DB)


@pytest.fixture
def acme():
    return SecureDataAccess("acme")


@pytest.fixture
def beta():
    return SecureDataAccess("beta")


@pytest.fixture
def gamma():
    return SecureDataAccess("gamma")
