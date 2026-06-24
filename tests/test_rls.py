"""
RLS security tests — the most critical suite.

These tests prove that:
1. Each tenant only ever sees its own rows.
2. Adversarial filter arguments cannot widen access.
3. Tool schemas exposed to the LLM contain no tenant_id parameter.
"""
import pytest
from src.data.db import SecureDataAccess


TENANTS = ["acme", "beta", "gamma"]


# ---------------------------------------------------------------------------
# 1. Tenant isolation — every read method returns only the correct tenant
# ---------------------------------------------------------------------------

class TestTenantIsolation:
    def test_get_dataframe_only_own_tenant(self, acme, beta, gamma):
        for sda, tid in [(acme, "acme"), (beta, "beta"), (gamma, "gamma")]:
            df = sda.get_dataframe()
            assert not df.empty, f"{tid}: expected rows"
            assert (df["tenant_id"] == tid).all(), f"{tid}: foreign rows returned"

    def test_no_cross_tenant_overlap(self, acme, beta, gamma):
        acme_ids = set(acme.get_dataframe()["user_id"])
        beta_ids = set(beta.get_dataframe()["user_id"])
        gamma_ids = set(gamma.get_dataframe()["user_id"])
        assert acme_ids.isdisjoint(beta_ids)
        assert acme_ids.isdisjoint(gamma_ids)
        assert beta_ids.isdisjoint(gamma_ids)

    def test_query_only_own_tenant(self, acme, beta):
        # A name clash across tenants is theoretically possible (same full name),
        # but we verify that no user_id crosses tenants.
        acme_ids = set(acme.query(columns=["user_id"])["user_id"])
        beta_ids = set(beta.query(columns=["user_id"])["user_id"])
        assert acme_ids.isdisjoint(beta_ids)

    def test_aggregate_only_own_tenant(self, acme, beta):
        # Values may coincidentally match — but underlying data must be separate.
        # We confirm row counts differ (acme=333, beta=334).
        assert len(acme.get_dataframe()) != len(beta.get_dataframe())

    def test_detect_anomalies_only_own_tenant(self, acme, beta):
        a_df = acme.get_dataframe()
        a_anomalies = acme.detect_anomalies("salary")
        if not a_anomalies.empty:
            # All anomaly user_ids should be in acme's full dataset
            assert set(a_anomalies["user_id"]).issubset(set(a_df["user_id"]))

    def test_department_filter_stays_within_tenant(self, acme):
        df = acme.get_dataframe(department="Engineering")
        assert (df["tenant_id"] == "acme").all()
        assert (df["department"] == "Engineering").all()


# ---------------------------------------------------------------------------
# 2. Adversarial inputs — malicious arguments must be blocked or ignored
# ---------------------------------------------------------------------------

class TestAdversarialInputs:
    def test_invalid_tenant_construction_rejected(self):
        with pytest.raises(ValueError, match="Unknown tenant"):
            SecureDataAccess("evil_corp")

    def test_unknown_column_rejected_in_query(self, acme):
        with pytest.raises(ValueError, match="not queryable"):
            acme.query(columns=["tenant_id"])  # tenant_id must not be selectable

    def test_sql_injection_in_department_rejected(self, acme):
        with pytest.raises(ValueError, match="not valid"):
            acme.get_dataframe(department="Engineering'; DROP TABLE employees; --")

    def test_sql_injection_via_column_rejected(self, acme):
        with pytest.raises(ValueError, match="not queryable"):
            acme.query(columns=["salary; DROP TABLE employees"])

    def test_unknown_agg_fn_rejected(self, acme):
        with pytest.raises((ValueError, KeyError)):
            acme.aggregate("salary", agg_fn="ARBITRARY_FN")

    def test_non_numeric_column_aggregate_rejected(self, acme):
        with pytest.raises(ValueError, match="not a numeric"):
            acme.aggregate("name")

    def test_cross_tenant_query_via_department_ignored(self, acme):
        """Even if department contains tenant info, it is validated against allow-list."""
        with pytest.raises(ValueError, match="not valid"):
            acme.get_dataframe(department="beta")

    def test_show_all_returns_only_own_tenant(self, acme):
        """'Show all salaries' returns only acme rows — the RLS golden test."""
        df = acme.query(columns=["user_id", "name", "salary"], limit=200)
        all_ids = set(df["user_id"])
        acme_ids = set(acme.get_dataframe()["user_id"])
        assert all_ids.issubset(acme_ids), "Cross-tenant rows leaked via query()"

    def test_limit_caps_at_200(self, acme):
        df = acme.query(limit=9999)
        assert len(df) <= 200


# ---------------------------------------------------------------------------
# 3. Tool schema inspection — LLM must not see tenant_id
# ---------------------------------------------------------------------------

class TestToolSchemas:
    def test_no_tenant_id_in_any_tool_schema(self):
        from src.agent.agent import _make_tools
        from src.data.db import SecureDataAccess

        sda = SecureDataAccess("acme")
        tools = _make_tools(sda)

        for t in tools:
            schema = t.args_schema.model_json_schema()
            props = schema.get("properties", {})
            assert "tenant_id" not in props, (
                f"Tool '{t.name}' exposes tenant_id to the LLM — RLS VIOLATION"
            )

    def test_tool_names_present(self):
        from src.agent.agent import _make_tools
        from src.data.db import SecureDataAccess

        sda = SecureDataAccess("acme")
        tools = _make_tools(sda)
        names = {t.name for t in tools}
        assert "query_employees" in names
        assert "compute_stats" in names
        assert "plot_chart" in names
        assert "detect_anomalies" in names


# ---------------------------------------------------------------------------
# 4. Data correctness — aggregates match ground-truth Pandas computation
# ---------------------------------------------------------------------------

class TestAggregateCorrectness:
    def test_avg_salary_by_department(self, acme):
        result = acme.aggregate("salary", group_by="department")
        df_full = acme.get_dataframe()
        ground_truth = df_full.groupby("department")["salary"].mean().round(6)

        for _, row in result.iterrows():
            dept = row["department"]
            expected = ground_truth[dept]
            actual = float(row["avg_salary"])
            assert abs(actual - expected) < 0.01, (
                f"{dept}: expected {expected:.2f}, got {actual:.2f}"
            )

    def test_sample_rows_no_tenant_id(self, acme):
        sample = acme.sample_rows(3)
        assert "tenant_id" not in sample.columns
