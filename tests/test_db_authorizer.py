"""
Defense-in-depth tests for the connection-level SQLite authorizer.

These prove that even *raw SQL* issued on a SecureDataAccess connection cannot:
  - read the base `employees` table directly, or
  - read another tenant's view.

This is the layer beneath the parameterized queries: even a future bug that
forgets a WHERE clause cannot leak across tenants.
"""
import sqlite3
import pytest
from src.data.db import SecureDataAccess, tenant_view


def _raw_conn(tenant_id: str):
    """Build a connection with the same authorizer SecureDataAccess uses."""
    sda = SecureDataAccess(tenant_id)
    return sda._connect()


class TestAuthorizer:
    def test_direct_base_table_read_denied(self):
        con = _raw_conn("acme")
        with pytest.raises(sqlite3.DatabaseError):
            con.execute("SELECT * FROM employees").fetchall()
        con.close()

    def test_other_tenant_view_denied(self):
        con = _raw_conn("acme")
        with pytest.raises(sqlite3.DatabaseError):
            con.execute(f"SELECT * FROM {tenant_view('beta')}").fetchall()
        con.close()

    def test_own_view_allowed(self):
        con = _raw_conn("acme")
        rows = con.execute(f"SELECT tenant_id FROM {tenant_view('acme')} LIMIT 5").fetchall()
        con.close()
        assert all(r["tenant_id"] == "acme" for r in rows)

    def test_union_attack_blocked(self):
        """A crafted UNION against the base table is denied by the authorizer."""
        con = _raw_conn("acme")
        with pytest.raises(sqlite3.DatabaseError):
            con.execute(
                f"SELECT name FROM {tenant_view('acme')} "
                "UNION SELECT name FROM employees"
            ).fetchall()
        con.close()
