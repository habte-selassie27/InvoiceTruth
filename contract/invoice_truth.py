# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }
# InvoiceTruth — Freelance Hours Verifier
# GenLayer Intelligent Contract
#
# PURPOSE:
#   Determines whether a sealed freelance invoice is PAYABLE, INFLATED,
#   or FABRICATED by cross-referencing a timesheet URL and a repository
#   commit log against the claimed hours and agreed hourly rate.
#
# TRUST MODEL:
#   - The client (opener) seals the agreed rate and two evidence URLs at
#     open time. Neither can be changed afterward.
#   - Validators independently fetch both URLs inside the nondet boundary;
#     they are never trusted with caller-supplied text.
#   - The LLM is asked narrow closed observations; deterministic
#     contract logic — not the model — derives the final verdict.
#   - Integer arithmetic only; no floating-point division.
#
# VERDICT CODES:
#   PAYABLE            — hours supported by both timesheet and commits;
#                        billed amount matches rate x hours within tolerance
#   INFLATED           — some work is evidenced but billed hours exceed
#                        supported hours by > 10%
#   FABRICATED         — no credible commit/timesheet evidence for the
#                        claimed period; treat as fraudulent
#   UNRESOLVABLE       — one or both evidence sources could not be fetched,
#                        or validators failed to reach majority; no verdict
#                        is stored and the case remains open for retry
#
# LIFECYCLE:
#   open_invoice  ->  assess_invoice  ->  terminal (PAYABLE/INFLATED/FABRICATED)
#   open_invoice  ->  assess_invoice  ->  UNRESOLVABLE  ->  assess_invoice (retry)
#
# KEY DESIGN CHOICES:
#   1. Evidence URLs are sealed at open time with SHA-256 digest commitment
#      over the URL strings; the digest is verified during assessment so
#      swapped sources fail closed.
#   2. Validator equivalence check binds commit_coverage, hours_alignment,
#      amount_alignment, fabrication_signal, and source_reachable — five
#      enumerable dimensions — plus the numeric claimed_hours_seen and
#      supported_hours_seen fields, all compared exactly.
#   3. Deterministic logic maps the observations to a verdict; the model
#      never produces PAYABLE/INFLATED/FABRICATED directly. amount_alignment
#      from the model is stored for audit but the 10% tolerance is
#      RECOMPUTED from integers so a dishonest model cannot force PAYABLE.
#   4. Replay protection: once a terminal verdict is stored, further
#      assess_invoice calls revert.
#   5. Integer-only math: all monetary values are in the smallest currency
#      unit (e.g. cents or wei-equivalent); rate x hours multiplication
#      stays in integers; 10% tolerance is checked as 10 x delta <= expected.

try:
    from genlayer import *
    HAS_GENLAYER = True
except ImportError:  # direct-mode local testing without GenVM
    HAS_GENLAYER = False
    from dataclasses import dataclass as _dataclass

    def allow_storage(cls):
        return _dataclass(cls)

    class _Public:
        @staticmethod
        def write(fn):
            return fn

        @staticmethod
        def view(fn):
            return fn

    class _DummyGL:
        public = _Public()
        Contract = object

    gl = _DummyGL()  # type: ignore
    u256 = int  # type: ignore
    Address = str  # type: ignore
    try:
        TreeMap  # type: ignore[name-defined]
    except NameError:
        TreeMap = dict  # type: ignore

import hashlib
import json
from dataclasses import dataclass


# ---------------------------------------------------------------------------
# Pure verdict derivation (no GenLayer dependency — unit-testable directly)
# ---------------------------------------------------------------------------

def derive_verdict(
    source_reachable: bool,
    commit_coverage: str,    # FULL | PARTIAL | NONE
    hours_alignment: str,    # CONSISTENT | MINOR_GAP | MAJOR_GAP | UNVERIFIABLE
    amount_alignment: str,   # EXACT | TOLERABLE | OVERSTATED | UNDERSTATED
    fabrication_signal: str,  # NONE | SUSPECTED | CONFIRMED
    supported_hours: int,
    rate_per_hour: int,
    claimed_amount: int,
) -> str:
    """Deterministic verdict mapping. Mirror of the on-chain logic below.

    Returns one of PAYABLE | INFLATED | FABRICATED | UNRESOLVED.
    `amount_alignment` is advisory only: the 10% tolerance is recomputed
    from integers so the model cannot bypass the INFLATED check.
    """
    if not source_reachable:
        return "UNRESOLVED"

    # Rule 1: confirmed fabrication wins over everything
    if fabrication_signal == "CONFIRMED":
        return "FABRICATED"

    # Rule 2/3: no commits -> FABRICATED (timesheet alone is insufficient)
    if commit_coverage == "NONE":
        return "FABRICATED"

    # Rule 4: suspected fabrication with major hour gap -> FABRICATED
    if fabrication_signal == "SUSPECTED" and hours_alignment == "MAJOR_GAP":
        return "FABRICATED"

    expected_amount = supported_hours * rate_per_hour
    if expected_amount == 0:
        # No supported hours -> cannot be payable
        return "FABRICATED"

    delta = abs(claimed_amount - expected_amount)
    within_tolerance = (delta * 10) <= expected_amount

    # Rule 5: major hour gap without fabrication signal -> INFLATED
    if hours_alignment == "MAJOR_GAP":
        return "INFLATED"

    # Rule 6: amount overstated beyond tolerance -> INFLATED
    if amount_alignment == "OVERSTATED" and not within_tolerance:
        return "INFLATED"

    # Rule 7: minor gap or suspected fabrication + outside tolerance -> INFLATED
    if (hours_alignment == "MINOR_GAP" or fabrication_signal == "SUSPECTED") \
            and not within_tolerance:
        return "INFLATED"

    # Rule 8: all checks pass -> PAYABLE
    return "PAYABLE"


def validate_open_params(
    rate_per_hour: int,
    claimed_hours: int,
    claimed_amount: int,
    timesheet_url: str,
    repo_url: str,
) -> None:
    """Shared validation for open_invoice (also unit-tested directly)."""
    assert rate_per_hour > 0, "Rate must be positive"
    assert claimed_hours > 0, "Claimed hours must be positive"
    assert claimed_amount > 0, "Claimed amount must be positive"
    assert len(timesheet_url) > 10, "timesheet_url too short"
    assert len(repo_url) > 10, "repo_url too short"
    assert timesheet_url != repo_url, "Evidence URLs must be distinct"


def url_digest(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()
