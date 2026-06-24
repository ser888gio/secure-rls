"""Pytest wrapper around the deterministic tool-level injection eval."""
from evals.injection_eval import _tool_level_eval


def test_no_tool_level_injection_leaks():
    results = _tool_level_eval()
    leaks = [r for r in results if not r.safe]
    assert not leaks, f"Injection leaks detected: {[(r.tenant, r.label) for r in leaks]}"
    assert len(results) >= 24  # 8 adversarial calls x 3 tenants
