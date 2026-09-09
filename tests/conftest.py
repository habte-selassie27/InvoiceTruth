"""Shared pytest fixtures for InvoiceTruth direct-mode tests.

The contract module uses `from genlayer import *` which only works inside GenVM.
For local testing, we install a lightweight stub of the `genlayer` module into
sys.modules BEFORE importing the contract, so the `try/except ImportError` path
is never triggered and the contract code loads cleanly.
"""

import os
import sys
import types

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

# ---------------------------------------------------------------------------
# GenLayer stub — installed once before any contract import
# ---------------------------------------------------------------------------

if "genlayer" not in sys.modules:
    _gl_mod = types.ModuleType("genlayer")
    _gl_mod.__path__ = []

    class _Public:
        @staticmethod
        def write(fn):
            return fn

        @staticmethod
        def view(fn):
            return fn

    class _Message:
        sender_address = "0x" + "a" * 40
        raw = {"datetime": "2026-01-01T00:00:00"}

    class _VM:
        class Return:
            def __init__(self, calldata):
                self.calldata = calldata
        class UserError(Exception):
            pass

    class _GL:
        public = _Public()
        Contract = object
        message = _Message()
        message_raw = _Message.raw
        vm = _VM()

        class nondet:
            class web:
                @staticmethod
                def get(url):
                    return ""
            @staticmethod
            def exec_prompt(prompt):
                return "{}"

    _gl_mod.gl = _GL()
    _gl_mod.u256 = int
    _gl_mod.Address = str
    _gl_mod.TreeMap = dict

    def _allow_storage(cls):
        return cls

    _gl_mod.allow_storage = _allow_storage

    sys.modules["genlayer"] = _gl_mod


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def rate() -> int:
    return 10_000


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
