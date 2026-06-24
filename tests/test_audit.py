"""Tests for audit logging of data access."""
import json
from src.security import audit
from src.data.db import SecureDataAccess


def test_log_access_writes_entry(tmp_path):
    log = tmp_path / "audit.log"
    entry = audit.log_access("acme", "acme_admin", "query", {"limit": 5}, 5, path=log)
    assert entry["tenant_id"] == "acme"
    assert entry["actor"] == "acme_admin"
    lines = log.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["row_count"] == 5


def test_read_recent_returns_last_n(tmp_path):
    log = tmp_path / "audit.log"
    for i in range(25):
        audit.log_access("acme", "acme_admin", "query", {"i": i}, i, path=log)
    recent = audit.read_recent(10, path=log)
    assert len(recent) == 10
    assert recent[-1]["params"]["i"] == 24  # most recent last


def test_secure_data_access_logs(tmp_path, monkeypatch):
    """A real query through SecureDataAccess produces an audit entry."""
    log = tmp_path / "audit.log"
    monkeypatch.setattr(audit, "AUDIT_PATH", log)

    sda = SecureDataAccess("acme", actor="acme_admin")
    df = sda.query(columns=["name", "salary"], limit=5)

    recent = audit.read_recent(5, path=log)
    assert any(e["action"] == "query" and e["tenant_id"] == "acme"
               for e in recent)
    assert recent[-1]["row_count"] == len(df)
    assert recent[-1]["actor"] == "acme_admin"
