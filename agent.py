"""
LangGraph ReAct agent with RLS-bound tools.

build_agent(tenant_id) returns an agent whose tools are closures over a
SecureDataAccess instance.  The LLM never sees or controls tenant_id —
it is bound below the tool boundary at construction time.
"""
from __future__ import annotations

import json
from typing import Any

import plotly.express as px
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from langchain_core.tools import tool
from langchain_ollama import ChatOllama
from langgraph.prebuilt import create_react_agent

from db import SecureDataAccess

OLLAMA_MODEL = "gemma4"


# ---------------------------------------------------------------------------
# Tool factory — closes over a SecureDataAccess bound to the session tenant
# ---------------------------------------------------------------------------

def _make_tools(sda: SecureDataAccess) -> list:
    """
    Return tool functions whose data access is fully bound to sda.
    The LLM-facing signatures intentionally omit any tenant parameter.
    """

    @tool
    def query_employees(
        department: str | None = None,
        columns: list[str] | None = None,
        limit: int = 20,
    ) -> str:
        """
        Query employee records for the current tenant.

        Args:
            department: Optional department filter (Engineering, Marketing, Sales, HR, Finance).
            columns: Optional list of columns to return (name, department, salary,
                     performance_score, hire_date, notes).
            limit: Maximum rows to return (default 20, max 200).

        Returns:
            JSON string of matching employee records.
        """
        df = sda.query(department=department, columns=columns, limit=limit)
        return df.to_json(orient="records", date_format="iso")

    @tool
    def compute_stats(
        metric: str = "salary",
        group_by: str | None = "department",
        agg_fn: str = "avg",
        department: str | None = None,
    ) -> str:
        """
        Compute aggregate statistics over employee data for the current tenant.

        Args:
            metric: Numeric column to aggregate (salary, performance_score).
            group_by: Column to group by (department, hire_date, etc.). Pass null for overall.
            agg_fn: Aggregation function — avg, sum, min, max, count.
            department: Optional department to restrict to before aggregating.

        Returns:
            JSON string of aggregated results.
        """
        df = sda.aggregate(metric=metric, group_by=group_by, agg_fn=agg_fn,
                           department=department)
        return df.to_json(orient="records")

    @tool
    def plot_chart(
        chart_type: str = "histogram",
        column: str = "salary",
        group_by: str | None = "department",
        department: str | None = None,
    ) -> str:
        """
        Generate a chart over the current tenant's employee data.

        Args:
            chart_type: Type of chart — histogram, bar, box, scatter.
            column: Primary numeric column (salary, performance_score).
            group_by: Column to color/group by (department).
            department: Optional department filter before plotting.

        Returns:
            JSON-encoded Plotly figure (pass back to the UI for rendering).
        """
        df = sda.get_dataframe(department=department)
        title_dept = f" — {department}" if department else ""

        if chart_type == "histogram":
            fig = px.histogram(
                df, x=column, color=group_by,
                title=f"{column.replace('_', ' ').title()} Distribution{title_dept}",
                barmode="overlay",
            )
        elif chart_type == "bar":
            if group_by:
                agg = df.groupby(group_by)[column].mean().reset_index()
                fig = px.bar(
                    agg, x=group_by, y=column,
                    title=f"Avg {column.replace('_', ' ').title()} by {group_by}{title_dept}",
                )
            else:
                fig = px.bar(df, y=column, title=f"{column}{title_dept}")
        elif chart_type == "box":
            fig = px.box(
                df, x=group_by, y=column,
                title=f"{column.replace('_', ' ').title()} by {group_by}{title_dept}",
            )
        elif chart_type == "scatter":
            fig = px.scatter(
                df, x="salary", y="performance_score", color=group_by,
                hover_data=["name"],
                title=f"Salary vs Performance{title_dept}",
            )
        else:
            return json.dumps({"error": f"Unknown chart type: {chart_type!r}"})

        return fig.to_json()

    @tool
    def detect_anomalies(column: str = "salary") -> str:
        """
        Identify statistical outliers (IQR method) in a numeric column
        within the current tenant's data.

        Args:
            column: Numeric column to analyse (salary, performance_score).

        Returns:
            JSON string of outlier employee records.
        """
        df = sda.detect_anomalies(column=column)
        if df.empty:
            return json.dumps({"message": "No anomalies detected.", "count": 0})
        return df.to_json(orient="records")

    return [query_employees, compute_stats, plot_chart, detect_anomalies]


# ---------------------------------------------------------------------------
# System prompt builder
# ---------------------------------------------------------------------------

def _system_prompt(sda: SecureDataAccess) -> str:
    sample = sda.sample_rows(3).to_string(index=False)
    schema = (
        "Schema: user_id (int), name (str), department (str), "
        "salary (int), performance_score (float 1–5), hire_date (date), notes (str)"
    )
    return f"""You are a secure data analyst assistant for an HR system.

{schema}

Sample rows from the current tenant:
{sample}

You have access to the following tools:
- query_employees: retrieve employee records with optional filters
- compute_stats: compute aggregates (avg/sum/min/max/count) by group
- plot_chart: generate charts (histogram, bar, box, scatter)
- detect_anomalies: find statistical outliers

IMPORTANT SECURITY RULES:
- You can ONLY access data for the current authenticated tenant.
- Never claim you can access or compare data from other companies or tenants.
- If asked to show data from other tenants or "all companies", explain that
  you only have access to the current tenant's data and show that instead.
- Always use your tools to answer — never fabricate numbers.

When you use a tool, briefly explain what you are doing before calling it.
After receiving results, give a clear, concise answer to the user's question.
If a chart is generated, mention it will be displayed in the panel below.
"""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_agent(tenant_id: str, model: str = OLLAMA_MODEL,
                actor: str | None = None) -> Any:
    """
    Build and return a LangGraph ReAct agent scoped to tenant_id.
    The returned agent accepts {'messages': [...]} and returns a state dict.
    actor (the authenticated username) is recorded in the audit log.
    """
    sda = SecureDataAccess(tenant_id, actor=actor)
    tools = _make_tools(sda)
    llm = ChatOllama(model=model, temperature=0)
    agent = create_react_agent(
        llm,
        tools,
        prompt=_system_prompt(sda),
    )
    return agent


def run_agent(agent: Any, user_message: str) -> dict:
    """
    Run the agent with a user message and return a structured result dict with:
      - answer: the final text response
      - tool_calls: list of {tool, input, output} dicts
      - figure_json: Plotly JSON if a chart was generated, else None
    """
    result = agent.invoke({"messages": [HumanMessage(content=user_message)]})
    messages = result.get("messages", [])

    tool_calls: list[dict] = []
    figure_json: str | None = None

    for msg in messages:
        # ToolMessage carries results from tool invocations
        if hasattr(msg, "name") and hasattr(msg, "content"):
            content = msg.content
            tool_calls.append({
                "tool": getattr(msg, "name", ""),
                "output": content[:500] + ("…" if len(content) > 500 else ""),
            })
            # Detect Plotly JSON (starts with {"data":)
            if content.strip().startswith('{"data"'):
                figure_json = content

    # Final answer is the last AIMessage
    answer = ""
    for msg in reversed(messages):
        if hasattr(msg, "content") and not hasattr(msg, "name"):
            if msg.content:
                answer = msg.content
                break

    return {"answer": answer, "tool_calls": tool_calls, "figure_json": figure_json}
