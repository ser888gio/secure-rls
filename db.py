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

DB_PATH = Path(__file__).parent / "employees.db"
CSV_PATH = Path(__file__).parent / "employees.csv"

ALLOWED_COLUMNS = frozenset(
    ["user_id", "tenant_id", "name", "department", "salary",
     "performance_score", "hire_date", "notes"]
)
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


def init_db(csv_path: str | Path = CSV_PATH, db_path: str | Path = DB_PATH) -> None:
    """Load employees.csv into SQLite and index by tenant_id."""
    df = pd.read_csv(csv_path)
    con = sqlite3.connect(db_path)
    df.to_sql("employees", con, if_exists="replace", index=False)
    con.execute("CREATE INDEX IF NOT EXISTS idx_tenant ON employees(tenant_id)")
    con.commit()
    con.close()


class SecureDataAccess:
    """
    Tenant-scoped data access.  tenant_id is bound at construction and is
    never accepted from the caller again — preventing any LLM-driven attempt
    to widen the scope.
    """

    def __init__(self, tenant_id: str, db_path: str | Path = DB_PATH) -> None:
        if tenant_id not in ("acme", "beta", "gamma"):
            raise ValueError(f"Unknown tenant: {tenant_id!r}")
        self._tenant_id = tenant_id
        self._db_path = str(db_path)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(self._db_path)
        con.row_factory = sqlite3.Row
        return con

    def _base_df(self) -> pd.DataFrame:
        """Return the full tenant-filtered DataFrame."""
        con = self._connect()
        df = pd.read_sql_query(
            "SELECT * FROM employees WHERE tenant_id = ?",
            con,
            params=(self._tenant_id,),
        )
        con.close()
        return df

    @staticmethod
    def _validate_column(col: str) -> str:
        if col not in ALLOWED_COLUMNS:
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
        return df.copy()

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
            select = ", ".join(ALLOWED_COLUMNS - {"tenant_id"})

        limit = min(max(1, limit), 200)

        if department is not None:
            self._validate_department(department)
            sql = (
                f"SELECT {select} FROM employees "
                "WHERE tenant_id = ? AND department = ? LIMIT ?"
            )
            params: tuple = (self._tenant_id, department, limit)
        else:
            sql = f"SELECT {select} FROM employees WHERE tenant_id = ? LIMIT ?"
            params = (self._tenant_id, limit)

        con = self._connect()
        df = pd.read_sql_query(sql, con, params=params)
        con.close()
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

        where_clauses = ["tenant_id = ?"]
        params_list: list = [self._tenant_id]

        if department is not None:
            self._validate_department(department)
            where_clauses.append("department = ?")
            params_list.append(department)

        where = " AND ".join(where_clauses)

        if group_by:
            sql = (
                f"SELECT {group_by}, {sql_agg}({metric}) AS {agg_fn}_{metric} "
                f"FROM employees WHERE {where} GROUP BY {group_by} ORDER BY {group_by}"
            )
        else:
            sql = (
                f"SELECT {sql_agg}({metric}) AS {agg_fn}_{metric} "
                f"FROM employees WHERE {where}"
            )

        con = self._connect()
        df = pd.read_sql_query(sql, con, params=tuple(params_list))
        con.close()
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
        return df[mask].drop(columns=["tenant_id"]).copy()

    def sample_rows(self, n: int = 3) -> pd.DataFrame:
        """Return n sample rows (no tenant_id) for embedding in the system prompt."""
        df = self._base_df().drop(columns=["tenant_id"])
        return df.head(n)
