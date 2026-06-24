"""
Append-only audit log for data access.

Every call into SecureDataAccess records: timestamp, tenant, actor (username),
action, parameters, and the number of rows returned.  Written as JSON lines to
audit.log (gitignored) so it can be tailed, shipped to a SIEM, or shown in the UI.
"""
from __future__ import annotations

import datetime
import json
from pathlib import Path
from threading import Lock

AUDIT_PATH = Path(__file__).parent.parent.parent / "audit.log"
_lock = Lock()


def log_access(
    tenant_id: str,
    actor: str,
    action: str,
    params: dict,
    row_count: int,
    path: Path | None = None,
) -> dict:
    """Append one audit entry and return it."""
    path = path or AUDIT_PATH
    entry = {
        "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "tenant_id": tenant_id,
        "actor": actor,
        "action": action,
        "params": params,
        "row_count": row_count,
    }
    with _lock:
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    return entry


def read_recent(n: int = 20, path: Path | None = None) -> list[dict]:
    """Return the most recent n audit entries (oldest first)."""
    path = path or AUDIT_PATH
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        lines = f.readlines()
    return [json.loads(line) for line in lines[-n:] if line.strip()]
