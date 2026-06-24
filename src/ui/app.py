"""Streamlit UI — secure multi-tenant data analyst chat."""
import sys
from pathlib import Path

# Ensure project root is on sys.path when launched via `streamlit run src/ui/app.py`
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import json

import plotly.graph_objects as go
import streamlit as st

from src.security import audit
from src.agent.agent import build_agent, run_agent
from src.data.db import DB_PATH, CSV_PATH, init_db

# ---------------------------------------------------------------------------
# Bootstrap DB on first run
# ---------------------------------------------------------------------------
if not DB_PATH.exists():
    if CSV_PATH.exists():
        init_db()
    else:
        st.error("employees.csv not found. Run `python src/data/gen_data.py` first.")
        st.stop()

# ---------------------------------------------------------------------------
# Hardcoded tenant credentials  (demo only — not production auth)
# ---------------------------------------------------------------------------
USERS: dict[str, dict] = {
    "acme_admin":  {"password": "acme123",  "tenant_id": "acme",  "display": "ACME Corp"},
    "beta_admin":  {"password": "beta123",  "tenant_id": "beta",  "display": "Beta Inc"},
    "gamma_admin": {"password": "gamma123", "tenant_id": "gamma", "display": "Gamma LLC"},
}

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Secure HR Analyst",
    page_icon="🔒",
    layout="wide",
)

# ---------------------------------------------------------------------------
# Session state helpers
# ---------------------------------------------------------------------------
def _init_state() -> None:
    defaults = {
        "authenticated": False,
        "tenant_id": None,
        "display_name": None,
        "username": None,
        "agent": None,
        "messages": [],       # {"role": "user"|"assistant", "content": str}
        "tool_calls": [],     # list of tool-call dicts from last turn
        "last_figure": None,  # Plotly JSON str
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

_init_state()

# ---------------------------------------------------------------------------
# Login screen
# ---------------------------------------------------------------------------
def show_login() -> None:
    st.title("🔒 Secure HR Analyst")
    st.caption("Multi-tenant conversational data analyst with Row-Level Security")

    with st.form("login_form"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Log in")

    if submitted:
        user = USERS.get(username)
        if user and user["password"] == password:
            st.session_state.authenticated = True
            st.session_state.username = username
            st.session_state.tenant_id = user["tenant_id"]
            st.session_state.display_name = user["display"]
            st.session_state.agent = build_agent(user["tenant_id"], actor=username)
            st.session_state.messages = []
            st.session_state.tool_calls = []
            st.session_state.last_figure = None
            st.rerun()
        else:
            st.error("Invalid credentials.")

    with st.expander("Demo credentials"):
        st.markdown(
            "| Username | Password | Tenant |\n"
            "|----------|----------|--------|\n"
            "| acme_admin | acme123 | ACME Corp |\n"
            "| beta_admin | beta123 | Beta Inc |\n"
            "| gamma_admin | gamma123 | Gamma LLC |"
        )

# ---------------------------------------------------------------------------
# Main app — shown after login
# ---------------------------------------------------------------------------
def show_app() -> None:
    tenant = st.session_state.tenant_id
    display = st.session_state.display_name

    # Sidebar
    with st.sidebar:
        st.markdown("### 🔒 Logged in as")
        st.markdown(f"**{st.session_state.username}**  \n`{display}` (`{tenant}`)")
        st.divider()
        st.markdown("### 💬 History")
        user_turns = [m["content"] for m in st.session_state.messages if m["role"] == "user"]
        if user_turns:
            for i, q in enumerate(user_turns, 1):
                st.markdown(f"{i}. {q}")
        else:
            st.caption("No messages yet. Start the conversation to build your history.")
        st.divider()
        if st.button("🚪 Logout", use_container_width=True):
            for k in list(st.session_state.keys()):
                del st.session_state[k]
            st.rerun()

    # Header
    st.title(f"🔒 Secure HR Analyst — {display}")
    st.caption(
        f"Your session is scoped to **{display}** (`{tenant}`). "
        "The agent can only access this tenant's data."
    )

    # Two-column layout: chat left, reasoning right
    chat_col, info_col = st.columns([3, 2])

    with chat_col:
        st.subheader("Chat")
        # Render message history
        for msg in st.session_state.messages:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

        # Sample questions — shown only before the session starts, then disappear
        if not st.session_state.messages:
            st.caption("Try one of these to get started:")
            samples = [
                "What is the average salary in Engineering?",
                "Show me a bar chart of average salary by department.",
                "Who are the top 5 highest paid employees?",
                "Show all salaries from every company.",
                "Detect salary anomalies.",
                "What's the avg performance score by department?",
            ]
            for q in samples:
                if st.button(q, key=f"sample_{q[:20]}", use_container_width=True):
                    st.session_state._pending_input = q

        # Pending input from sample buttons
        pending = st.session_state.pop("_pending_input", None)
        user_input = st.chat_input("Ask about your employees…") or pending

        if user_input:
            st.session_state.messages.append({"role": "user", "content": user_input})
            with st.chat_message("user"):
                st.markdown(user_input)

            with st.chat_message("assistant"):
                with st.spinner("Thinking…"):
                    result = run_agent(st.session_state.agent, user_input)

                answer = result["answer"]
                st.markdown(answer)
                st.session_state.messages.append({"role": "assistant", "content": answer})
                st.session_state.tool_calls = result["tool_calls"]
                st.session_state.last_figure = result.get("figure_json")

    with info_col:
        st.subheader("Reasoning & Tool Calls")

        if st.session_state.tool_calls:
            for i, tc in enumerate(st.session_state.tool_calls, 1):
                with st.expander(f"Tool {i}: `{tc['tool']}`", expanded=(i == 1)):
                    st.code(tc["output"], language="json")
        else:
            st.info("Tool calls will appear here after your first query.")

        if st.session_state.last_figure:
            st.subheader("Chart")
            try:
                fig = go.Figure(json.loads(st.session_state.last_figure))
                st.plotly_chart(fig, use_container_width=True)
            except Exception:
                st.warning("Could not render chart.")

        st.divider()
        with st.expander("Security status"):
            st.markdown(
                f"- **Authenticated tenant:** `{tenant}`\n"
                "- **RLS enforcement:** tenant-scoped view + connection authorizer\n"
                "- **tenant_id in tool schemas:** ❌ No (bound server-side)\n"
                "- **Raw SQL accepted by tools:** ❌ No\n"
                "- **Column allow-list enforced:** ✅ Yes"
            )

        with st.expander("Audit log (recent data access)"):
            entries = [e for e in audit.read_recent(15) if e["tenant_id"] == tenant]
            if entries:
                st.dataframe(
                    [
                        {
                            "time": e["ts"].split("T")[1][:8],
                            "actor": e["actor"],
                            "action": e["action"],
                            "rows": e["row_count"],
                        }
                        for e in reversed(entries)
                    ],
                    use_container_width=True,
                    hide_index=True,
                )
            else:
                st.caption("No data access recorded yet this session.")

# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------
if st.session_state.authenticated:
    show_app()
else:
    show_login()
