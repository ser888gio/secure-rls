"""
Secure data access layer.

SecureDataAccess is the only entry point to employee data.
It binds a tenant_id at construction time and injects it into every
parameterized query — no method accepts raw SQL or a caller-supplied tenant.
"""
import sqlite3
from pathlib import Path
from typing import Literal

import pandas as pd

from src.security import audit

_ARTIFACTS = Path(__file__).parent.parent.parent / "data"

DB_PATH = _ARTIFACTS / "employees.db"
CSV_PATH = _ARTIFACTS / "employees.csv"

TENANTS = ("acme", "beta", "gamma")

ALLOWED_COLUMNS = frozenset(
    ["user_id", "tenant_id", "name", "department", "salary",
     "performance_score", "hire_date", "notes"]
)
# Columns callers (and the LLM) may request — tenant_id is never exposed
QUERYABLE_COLUMNS = ALLOWED_COLUMNS - {"tenant_id"}
ALLOWED_DEPARTMENTS = frozenset(
    ["Engineering", "Marketing", "Sales", "HR", "Finance"]
)
ALLOWED_AGG_FNS: dict[str, str] = {
    "avg": "AVG",
    "sum": "SUM",
    "min": "MIN",
    "max": "MAX",
    "count": "COUNT",
}
NUMERIC_COLUMNS = frozenset(["salary", "performance_score", "user_id"])


def tenant_view(tenant_id: str) -> str:
    """Return the per-tenant view name (tenant_id is allow-listed by callers)."""
    return f"employees_{tenant_id}"


def init_db(csv_path: str | Path = CSV_PATH, db_path: str | Path = DB_PATH) -> None:
    """
    Load employees.csv into SQLite, index by tenant_id, and create one
    pre-filtered VIEW per tenant.  SecureDataAccess only ever reads through
    its tenant's view — see the connection authorizer in SecureDataAccess.
    """
    df = pd.read_csv(csv_path)
    con = sqlite3.connect(db_path)
    df.to_sql("employees", con, if_exists="replace", index=False)
    con.execute("CREATE INDEX IF NOT EXISTS idx_tenant ON employees(tenant_id)")
    for tid in TENANTS:
        view = tenant_view(tid)
        con.execute(f"DROP VIEW IF EXISTS {view}")
        # tid is allow-listed (member of TENANTS); safe to embed, but also bound
        con.execute(
            f"CREATE VIEW {view} AS SELECT * FROM employees WHERE tenant_id = '{tid}'"
        )
    con.commit()
    con.close()


class SecureDataAccess:
    """
    Tenant-scoped data access.  tenant_id is bound at construction and is
    never accepted from the caller again — preventing any LLM-driven attempt
    to widen the scope.
    """

    def __init__(
        self,
        tenant_id: str,
        db_path: str | Path = DB_PATH,
        actor: str | None = None,
    ) -> None:
        if tenant_id not in TENANTS:
            raise ValueError(f"Unknown tenant: {tenant_id!r}")
        self._tenant_id = tenant_id
        self._db_path = str(db_path)
        self._view = tenant_view(tenant_id)
        # actor = authenticated username; defaults to tenant for non-UI callers
        self._actor = actor or tenant_id

    def _audit(self, action: str, params: dict, row_count: int) -> None:
        audit.log_access(self._tenant_id, self._actor, action, params, row_count)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _authorizer(self, action, arg1, arg2, db_name, trigger):
        """
        Connection-level last line of defense.  Even raw SQL on this connection
        cannot read the base `employees` table directly or any other tenant's
        view — reads of the base table are only permitted when expanded through
        THIS tenant's view (SQLite passes the view name as `trigger`).
        """
        if action == sqlite3.SQLITE_READ:
            table = arg1
            if table == "employees":
                # base-table read is only allowed via this tenant's own view
                return sqlite3.SQLITE_OK if trigger == self._view else sqlite3.SQLITE_DENY
            if table.startswith("employees_") and table != self._view:
                # any other tenant's view is off-limits
                return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK

    def _connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(self._db_path)
        con.row_factory = sqlite3.Row
        con.set_authorizer(self._authorizer)
        return con

    def _base_df(self) -> pd.DataFrame:
        """Return the full tenant-filtered DataFrame (via the tenant view)."""
        con = self._connect()
        df = pd.read_sql_query(f"SELECT * FROM {self._view}", con)
        con.close()
        return df

    @staticmethod
    def _validate_column(col: str) -> str:
        if col not in QUERYABLE_COLUMNS:
            raise ValueError(f"Column {col!r} is not queryable.")
        return col

    @staticmethod
    def _validate_department(dept: str) -> str:
        if dept not in ALLOWED_DEPARTMENTS:
            raise ValueError(f"Department {dept!r} is not valid.")
        return dept

    # ------------------------------------------------------------------
    # Public API — all methods are tenant-scoped by construction
    # ------------------------------------------------------------------

    def get_dataframe(self, department: str | None = None) -> pd.DataFrame:
        """
        Return a tenant-filtered DataFrame, optionally narrowed to one department.
        This is the raw data surface; callers receive a copy, not a live view.
        """
        df = self._base_df()
        if department is not None:
            self._validate_department(department)
            df = df[df["department"] == department]
        df = df.copy()
        self._audit("get_dataframe", {"department": department}, len(df))
        return df

    def query(
        self,
        department: str | None = None,
        columns: list[str] | None = None,
        limit: int = 50,
    ) -> pd.DataFrame:
        """
        Return selected columns for the tenant, optionally filtered by department.
        columns must be a subset of ALLOWED_COLUMNS.
        limit caps row count to prevent accidental full-table dumps.
        """
        if columns:
            for col in columns:
                self._validate_column(col)
            select = ", ".join(columns)
        else:
            select = ", ".join(QUERYABLE_COLUMNS)

        limit = min(max(1, limit), 200)

        if department is not None:
            self._validate_department(department)
            sql = (
                f"SELECT {select} FROM {self._view} "
                "WHERE department = ? LIMIT ?"
            )
            params: tuple = (department, limit)
        else:
            sql = f"SELECT {select} FROM {self._view} LIMIT ?"
            params = (limit,)

        con = self._connect()
        df = pd.read_sql_query(sql, con, params=params)
        con.close()
        self._audit(
            "query",
            {"department": department, "columns": columns, "limit": limit},
            len(df),
        )
        return df

    def aggregate(
        self,
        metric: str,
        group_by: str | None = None,
        agg_fn: Literal["avg", "sum", "min", "max", "count"] = "avg",
        department: str | None = None,
    ) -> pd.DataFrame:
        """
        Compute an aggregate over a numeric column, optionally grouped.
        metric and group_by must be in ALLOWED_COLUMNS; agg_fn in ALLOWED_AGG_FNS.
        """
        self._validate_column(metric)
        if metric not in NUMERIC_COLUMNS:
            raise ValueError(f"{metric!r} is not a numeric column.")
        if group_by is not None:
            self._validate_column(group_by)

        sql_agg = ALLOWED_AGG_FNS.get(agg_fn)
        if sql_agg is None:
            raise ValueError(f"Unsupported aggregation: {agg_fn!r}")

        params_list: list = []
        where = ""
        if department is not None:
            self._validate_department(department)
            where = "WHERE department = ?"
            params_list.append(department)

        if group_by:
            sql = (
                f"SELECT {group_by}, {sql_agg}({metric}) AS {agg_fn}_{metric} "
                f"FROM {self._view} {where} GROUP BY {group_by} ORDER BY {group_by}"
            )
        else:
            sql = (
                f"SELECT {sql_agg}({metric}) AS {agg_fn}_{metric} "
                f"FROM {self._view} {where}"
            )

        con = self._connect()
        df = pd.read_sql_query(sql, con, params=tuple(params_list))
        con.close()
        self._audit(
            "aggregate",
            {"metric": metric, "group_by": group_by, "agg_fn": agg_fn,
             "department": department},
            len(df),
        )
        return df

    def detect_anomalies(self, column: str = "salary") -> pd.DataFrame:
        """
        Return rows where column value is an outlier (IQR method) within tenant data.
        """
        self._validate_column(column)
        if column not in NUMERIC_COLUMNS:
            raise ValueError(f"{column!r} is not numeric.")

        df = self._base_df()
        q1 = df[column].quantile(0.25)
        q3 = df[column].quantile(0.75)
        iqr = q3 - q1
        mask = (df[column] < q1 - 1.5 * iqr) | (df[column] > q3 + 1.5 * iqr)
        result = df[mask].drop(columns=["tenant_id"]).copy()
        self._audit("detect_anomalies", {"column": column}, len(result))
        return result

    def sample_rows(self, n: int = 3) -> pd.DataFrame:
        """Return n sample rows (no tenant_id) for embedding in the system prompt."""
        df = self._base_df().drop(columns=["tenant_id"])
        return df.head(n)
