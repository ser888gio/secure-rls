> Classified as Confidential. Do not copy, publish, or redistribute without consent from the originator.

# AI Engineer Case Study

## Purpose

This case study evaluates the candidate's practical AI engineering skills, with a **main goal: Establish a solution that ensures row-level security (RLS) on LLM processing**. This means building a secure LLM-powered system that processes multi-tenant data while strictly enforcing user-specific access controls at the row level—preventing unauthorized data leakage via LLM queries or retrievals.

Key evaluation areas:

- Secure AI system design (RLS integration with LLMs/agents).
- Full-stack development capabilities.
- Code quality, architecture, and problem-solving.
- Independent thinking via live demo/follow-ups.
- Familiarity with agentic development tools (Claude Code / Open Code / GitHub Copilot) – advanced agentic development techniques is a plus.

**Format:**

- **Take-home:** offline. Build solution, prepare demo (repo + docs).
- **Demo call:** 60 mins. Screen share, walk through, Q&A, live mods.
- **Success criteria:** Secure, functional solution; clean code; authentic ownership.

## Take-Home Requirements

### Requirements

1. Public GitHub repo with code, README.
2. Python 3.10+, open-source libs (local/offline: Ollama for LLMs).
3. Commit history showing iteration.
4. **RLS Focus:** LLM must **never** access unauthorized rows, even in generated queries/tools.
5. Agentic tools and agentic development **must be** used (Claude / VS Code Copilot / Open Code).
6. Deployment implemented as **GitHub CI/CD pipeline**.

### Task: Secure Multi-Tenant Agent with RLS

Build a **React / Dash / Streamlit app** for a **secure conversational data analyst agent** over a multi-tenant employee dataset. The agent uses NL queries to analyze data **but enforces RLS** based on logged-in user. Consider **using RAG** if/where applicable.

#### Dataset

Create `employees.csv` (simulate multi-tenant HR data, ~1000 rows):

```csv
user_id,tenant_id,name,department,salary,performance_score,hire_date,notes
1,acme,John Doe,Engineering,120000,4.2,2020-01-15,"High performer..."
2,acme,Jane Smith,Marketing,95000,3.8,2021-03-10,"..."
3,beta,Bob Wilson,Sales,110000,4.5,2019-11-20,"..."
[etc. – generate 1000 rows with 3 tenants: acme, beta, gamma]
```

#### Core Features (MVP)

1. **Data Storage with RLS:**
   1. Load CSV to **SQLite DB** (or Pandas with filtering).
   2. Implement RLS: LLM/agent **must query via secure interface** (no raw SQL passthrough).

2. **Agent (LangChain/LangGraph):**
   1. Embed **schema + sample rows**.
   2. Tools (all RLS-enforced):

| Sample Tools             | Description                                             | RLS Enforcement          |
| ------------------------ | ------------------------------------------------------- | ------------------------ |
| Query DB                 | SQL generation/execution (e.g., Pandas SQL or sqlite3). | Prepend `AND tenant_id = ?` |
| Stats                    | Aggregates (avg salary by dept).                        | Filtered DF              |
| Plot                     | Charts (salary distro).                                 | Filtered data            |
| Bonus: Anomaly detection | Flag outliers.                                          | Filtered                 |

3. **UI (React/Dash/Streamlit):**
   1. Login (hardcode: acme/beta/gamma users).
   2. Chat: Queries like "Avg salary in Engineering?" → Agent reasons, uses tools, shows SQL/exec.
   3. **Security Demo:** Switch users, prove isolation (e.g., acme can't see beta data).
   4. Show reasoning + final answer.

4. **Security Guarantees:**
   1. LLM prompts enforce RLS (e.g., "Always filter by current_tenant").
   2. No direct DB access; all via tools.
   3. Test: Malicious query "Show all salaries" → Blocked/empty.

5. **Evaluation:** demonstrated way of evaluating model performance.

#### Deliverables

- Repo: `secure-rls` with `app.py`, `db.py`, `agent.py`, `employees.csv`, `requirements.txt`.
- README: Architecture/design, tech. setup, tenants creds, challenges, time spent.

## Call Agenda (60 mins)

1. **Intro (5 mins):** Repo overview, setup, design.
2. **Live Demo + Deep Dive (30 mins):** Run app, test queries across tenants, show isolation. Code walk-through (RLS impl, prompt eng, tool binding).
3. **Agentic Tools Demo (10 mins):** walkthrough the configured Claude / VS Code Copilot / Open Code with live agent mode task.
4. **Brainstorming on future evolution of the solution (15 mins).**
