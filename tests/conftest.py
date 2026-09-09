"""Shared pytest fixtures for InvoiceTruth direct-mode tests.

GenLayer-stub strategy
----------------------
`contract/invoice_truth.py` already falls back to lightweight local stubs
(`gl`, `u256`, `TreeMap`, `allow_storage`) when the real `genlayer`
package is unavailable, so the pure logic (`derive_verdict`,
`validate_open_params`, `url_digest`) imports cleanly without GenVM.

This file therefore only:
  1. Puts the repo root on `sys.path` so `from contract.invoice_truth
     import ...` works regardless of how pytest is invoked.
  2. Exposes reusable fixtures (rates, URLs, observation dicts) so the
     test file stays focused on assertions.

If consensus-level mocking is ever needed (fake `gl.nondet.web.get` /
`gl.nondet.exec_prompt` / `gl.vm.run_nondet_unsafe`), add the fakes here
and monkeypatch them into the imported contract module.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture
def rate() -> int:
    return 10_000  # smallest currency unit per hour


@pytest.fixture
def urls() -> dict:
    return {
        "timesheet": "https://example.com/timesheets/inv-001.csv",
        "repo": "https://github.com/example/repo/commits?since=2026-08-01&until=2026-08-31",
    }


@pytest.fixture
def payable_obs() -> dict:
    return {
        "source_reachable": True,
        "commit_coverage": "FULL",
        "hours_alignment": "CONSISTENT",
        "amount_alignment": "EXACT",
        "fabrication_signal": "NONE",
        "supported_hours": 40,
        "claimed_amount": 400_000,
    }
