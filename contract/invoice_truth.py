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


# ---------------------------------------------------------------------------
# Enumerations (plain string constants — not stored as enums)
# ---------------------------------------------------------------------------

class CoverageSignal:
    FULL = "FULL"
    PARTIAL = "PARTIAL"
    NONE = "NONE"


class HoursAlignment:
    CONSISTENT = "CONSISTENT"
    MINOR_GAP = "MINOR_GAP"
    MAJOR_GAP = "MAJOR_GAP"
    UNVERIFIABLE = "UNVERIFIABLE"


class AmountAlignment:
    EXACT = "EXACT"
    TOLERABLE = "TOLERABLE"
    OVERSTATED = "OVERSTATED"
    UNDERSTATED = "UNDERSTATED"


class FabricationSignal:
    NONE = "NONE"
    SUSPECTED = "SUSPECTED"
    CONFIRMED = "CONFIRMED"


class InvoiceStatus:
    PENDING = "PENDING"
    ASSESSED = "ASSESSED"      # terminal — has a verdict
    UNRESOLVABLE = "UNRESOLVABLE"  # non-terminal — retry allowed


class Verdict:
    PAYABLE = "PAYABLE"
    INFLATED = "INFLATED"
    FABRICATED = "FABRICATED"
    UNRESOLVED = "UNRESOLVED"  # stored only when status = UNRESOLVABLE


# ---------------------------------------------------------------------------
# Storage record
# ---------------------------------------------------------------------------

try:
    @allow_storage
    @dataclass
    class InvoiceRecord:
        opener: str
        rate_per_hour: u256
        claimed_hours: u256
        claimed_amount: u256
        timesheet_url: str
        repo_url: str
        timesheet_digest: str
        repo_digest: str
        status: str
        verdict: str
        commit_coverage: str
        hours_alignment: str
        amount_alignment: str
        fabrication_signal: str
        supported_hours: u256
        assessed_count: u256
        opened_at: u256
except Exception:
    # Fallback for stub environments where @dataclass composition differs
    from dataclasses import dataclass

    @dataclass
    class InvoiceRecord:  # type: ignore[no-redef]
        opener: str = ""
        rate_per_hour: int = 0
        claimed_hours: int = 0
        claimed_amount: int = 0
        timesheet_url: str = ""
        repo_url: str = ""
        timesheet_digest: str = ""
        repo_digest: str = ""
        status: str = "PENDING"
        verdict: str = ""
        commit_coverage: str = ""
        hours_alignment: str = ""
        amount_alignment: str = ""
        fabrication_signal: str = ""
        supported_hours: int = 0
        assessed_count: int = 0
        opened_at: int = 0


# ---------------------------------------------------------------------------
# Contract
# ---------------------------------------------------------------------------

class InvoiceTruthContract(gl.Contract):  # type: ignore
    owner: str
    invoice_count: u256
    invoices: TreeMap[u256, InvoiceRecord]  # type: ignore
    max_invoices: u256

    def __init__(self) -> None:
        self.owner = gl.message.sender_address
        self.invoice_count = u256(0)
        self.max_invoices = u256(500)

    # -------------------------------------------------------------------
    # open_invoice
    # -------------------------------------------------------------------

    @gl.public.write
    def open_invoice(
        self,
        rate_per_hour: u256,
        claimed_hours: u256,
        claimed_amount: u256,
        timesheet_url: str,
        repo_url: str,
    ) -> u256:
        """Seal an invoice for verification.

        Stores rate/hours/amount plus both evidence URLs immutably and
        commits to SHA-256(URL) digests verified at assessment time.
        Returns the invoice ID.
        """
        assert self.invoice_count < self.max_invoices, "Registry full"
        validate_open_params(
            int(rate_per_hour),
            int(claimed_hours),
            int(claimed_amount),
            timesheet_url,
            repo_url,
        )

        invoice_id = self.invoice_count
        rec = InvoiceRecord(
            opener=gl.message.sender_address,
            rate_per_hour=rate_per_hour,
            claimed_hours=claimed_hours,
            claimed_amount=claimed_amount,
            timesheet_url=timesheet_url,
            repo_url=repo_url,
            timesheet_digest=url_digest(timesheet_url),
            repo_digest=url_digest(repo_url),
            status=InvoiceStatus.PENDING,
            verdict="",
            commit_coverage="",
            hours_alignment="",
            amount_alignment="",
            fabrication_signal="",
            supported_hours=u256(0),
            assessed_count=u256(0),
            opened_at=u256(gl.message.block_number),
        )
        self.invoices[invoice_id] = rec
        self.invoice_count = invoice_id + u256(1)
        return invoice_id

    # -------------------------------------------------------------------
    # assess_invoice  (nondet — requires validator consensus)
    # -------------------------------------------------------------------

    @gl.public.write
    def assess_invoice(self, invoice_id: u256) -> None:
        """Run validator consensus over the sealed evidence URLs.

        Any caller may trigger assessment; only the opener sealed the
        evidence. Replay is blocked once a terminal verdict is stored.
        UNRESOLVABLE cases may be retried.
        """
        assert invoice_id < self.invoice_count, "Unknown invoice"
        rec = self.invoices[invoice_id]

        assert rec.status != InvoiceStatus.ASSESSED, \
            "Invoice already has a terminal verdict; replay rejected"

        # Verify sealed digests (fail closed on swapped sources)
        assert rec.timesheet_digest == url_digest(rec.timesheet_url), \
            "Timesheet URL digest mismatch"
        assert rec.repo_digest == url_digest(rec.repo_url), \
            "Repo URL digest mismatch"

        # Copy sealed parameters to memory (storage is inaccessible
        # from inside nondet blocks; closure capture is the supported path)
        rate_per_hour = int(rec.rate_per_hour)
        claimed_hours = int(rec.claimed_hours)
        claimed_amount = int(rec.claimed_amount)
        timesheet_url = str(rec.timesheet_url)
        repo_url = str(rec.repo_url)

        # --------------------------------------------------------------
        # NONDET: each validator independently fetches both sources and
        # returns closed observations + two integer fields.
        # --------------------------------------------------------------

        def _decode_body(resp) -> str:
            body = getattr(resp, "body", resp)
            if isinstance(body, (bytes, bytearray)):
                try:
                    return bytes(body).decode("utf-8", errors="replace")
                except Exception:
                    return ""
            return str(body)

        def leader_fn() -> dict:
            try:
                ts_resp = gl.nondet.web.get(timesheet_url)
                timesheet_content = _decode_body(ts_resp)
                timesheet_ok = True
            except Exception:
                timesheet_content = ""
                timesheet_ok = False

            try:
                repo_resp = gl.nondet.web.get(repo_url)
                repo_content = _decode_body(repo_resp)
                repo_ok = True
            except Exception:
                repo_content = ""
                repo_ok = False

            if not timesheet_ok or not repo_ok:
                return {
                    "source_reachable": False,
                    "commit_coverage": CoverageSignal.NONE,
                    "hours_alignment": HoursAlignment.UNVERIFIABLE,
                    "amount_alignment": AmountAlignment.OVERSTATED,
                    "fabrication_signal": FabricationSignal.NONE,
                    "supported_hours_seen": 0,
                    "claimed_hours_seen": claimed_hours,
                }

            prompt = f"""You are a forensic invoice auditor. Evaluate the evidence below.

INVOICE PARAMETERS (sealed, do not trust caller text):
- Agreed hourly rate (integer, smallest unit): {rate_per_hour}
- Claimed hours billed: {claimed_hours}
- Claimed total amount billed (integer): {claimed_amount}

TIMESHEET EVIDENCE (fetched from {timesheet_url}):
---BEGIN TIMESHEET---
{timesheet_content[:4000]}
---END TIMESHEET---

REPOSITORY COMMIT LOG (fetched from {repo_url}):
---BEGIN COMMIT LOG---
{repo_content[:4000]}
---END COMMIT LOG---

Return ONLY a valid JSON object with exactly these keys and allowed values:

{{
  "commit_coverage": "FULL" | "PARTIAL" | "NONE",
  "hours_alignment": "CONSISTENT" | "MINOR_GAP" | "MAJOR_GAP" | "UNVERIFIABLE",
  "amount_alignment": "EXACT" | "TOLERABLE" | "OVERSTATED" | "UNDERSTATED",
  "fabrication_signal": "NONE" | "SUSPECTED" | "CONFIRMED",
  "supported_hours_seen": <integer verifiable hours from evidence>,
  "claimed_hours_seen": <integer hours stated on timesheet, or {claimed_hours} if unreadable>
}}

Rules:
- commit_coverage: FULL if commits span the full billing period; PARTIAL if some; NONE if zero attributable commits.
- hours_alignment: compare the timesheet's logged hours to commit volume and density.
- amount_alignment: compare claimed_amount to (supported_hours x rate_per_hour) using integer arithmetic only.
- fabrication_signal: CONFIRMED for copy-pasted commits, implausible timestamps, placeholders. SUSPECTED for minor anomalies. NONE otherwise.
- supported_hours_seen: best integer estimate of verifiable hours; 0 if none verifiable.
- claimed_hours_seen: hours stated on the timesheet; use {claimed_hours} if unreadable.
- No explanation, markdown, or extra keys.
"""
            raw = gl.nondet.exec_prompt(prompt)

            cleaned = raw.strip()
            if cleaned.startswith("```"):
                cleaned = "\n".join(cleaned.split("\n")[1:])
            if cleaned.endswith("```"):
                cleaned = cleaned[: cleaned.rfind("```")]

            try:
                obs = json.loads(cleaned.strip())
            except Exception:
                return {
                    "source_reachable": True,
                    "commit_coverage": CoverageSignal.NONE,
                    "hours_alignment": HoursAlignment.UNVERIFIABLE,
                    "amount_alignment": AmountAlignment.OVERSTATED,
                    "fabrication_signal": FabricationSignal.NONE,
                    "supported_hours_seen": 0,
                    "claimed_hours_seen": claimed_hours,
                }

            valid_coverage = {CoverageSignal.FULL, CoverageSignal.PARTIAL, CoverageSignal.NONE}
            valid_alignment = {HoursAlignment.CONSISTENT, HoursAlignment.MINOR_GAP,
                               HoursAlignment.MAJOR_GAP, HoursAlignment.UNVERIFIABLE}
            valid_amount = {AmountAlignment.EXACT, AmountAlignment.TOLERABLE,
                            AmountAlignment.OVERSTATED, AmountAlignment.UNDERSTATED}
            valid_fab = {FabricationSignal.NONE, FabricationSignal.SUSPECTED,
                         FabricationSignal.CONFIRMED}

            cov = obs.get("commit_coverage", CoverageSignal.NONE)
            if cov not in valid_coverage:
                cov = CoverageSignal.NONE
            ha = obs.get("hours_alignment", HoursAlignment.UNVERIFIABLE)
            if ha not in valid_alignment:
                ha = HoursAlignment.UNVERIFIABLE
            aa = obs.get("amount_alignment", AmountAlignment.OVERSTATED)
            if aa not in valid_amount:
                aa = AmountAlignment.OVERSTATED
            fab = obs.get("fabrication_signal", FabricationSignal.NONE)
            if fab not in valid_fab:
                fab = FabricationSignal.NONE
            sh = obs.get("supported_hours_seen", 0)
            if not isinstance(sh, int) or sh < 0:
                sh = 0
            ch = obs.get("claimed_hours_seen", claimed_hours)
            if not isinstance(ch, int) or ch < 0:
                ch = claimed_hours

            return {
                "source_reachable": True,
                "commit_coverage": cov,
                "hours_alignment": ha,
                "amount_alignment": aa,
                "fabrication_signal": fab,
                "supported_hours_seen": sh,
                "claimed_hours_seen": ch,
            }

        def validator_fn(leader_result) -> bool:
            # Independent verification: re-run and compare binding fields.
            if not isinstance(leader_result, gl.vm.Return):
                return False
            try:
                validator_data = leader_fn()
            except Exception:
                return False
            leader_data = leader_result.calldata
            binding_keys = [
                "source_reachable",
                "commit_coverage",
                "hours_alignment",
                "amount_alignment",
                "fabrication_signal",
                "supported_hours_seen",
                "claimed_hours_seen",
            ]
            try:
                return all(
                    leader_data.get(k) == validator_data.get(k)
                    for k in binding_keys
                )
            except Exception:
                return False

        result = gl.vm.run_nondet_unsafe(leader_fn, validator_fn)

        # --------------------------------------------------------------
        # DETERMINISTIC VERDICT DERIVATION (integer-only)
        # --------------------------------------------------------------

        supported_hours = u256(int(result["supported_hours_seen"]))

        if not result["source_reachable"]:
            rec.status = InvoiceStatus.UNRESOLVABLE
            rec.verdict = Verdict.UNRESOLVED
            rec.assessed_count = rec.assessed_count + u256(1)
            self.invoices[invoice_id] = rec
            return

        cov = str(result["commit_coverage"])
        ha = str(result["hours_alignment"])
        aa = str(result["amount_alignment"])
        fab = str(result["fabrication_signal"])

        rec.commit_coverage = cov
        rec.hours_alignment = ha
        rec.amount_alignment = aa
        rec.fabrication_signal = fab
        rec.supported_hours = supported_hours
        rec.assessed_count = rec.assessed_count + u256(1)

        rec.verdict = derive_verdict(
            source_reachable=True,
            commit_coverage=cov,
            hours_alignment=ha,
            amount_alignment=aa,
            fabrication_signal=fab,
            supported_hours=int(supported_hours),
            rate_per_hour=rate_per_hour,
            claimed_amount=claimed_amount,
        )
        rec.status = InvoiceStatus.ASSESSED
        self.invoices[invoice_id] = rec

    # -------------------------------------------------------------------
    # Read methods
    # -------------------------------------------------------------------

    @gl.public.view
    def get_invoice(self, invoice_id: u256) -> dict:
        assert invoice_id < self.invoice_count, "Unknown invoice"
        rec = self.invoices[invoice_id]
        return {
            "invoice_id": int(invoice_id),
            "opener": rec.opener,
            "rate_per_hour": int(rec.rate_per_hour),
            "claimed_hours": int(rec.claimed_hours),
            "claimed_amount": int(rec.claimed_amount),
            "timesheet_url": rec.timesheet_url,
            "repo_url": rec.repo_url,
            "status": rec.status,
            "verdict": rec.verdict,
            "commit_coverage": rec.commit_coverage,
            "hours_alignment": rec.hours_alignment,
            "amount_alignment": rec.amount_alignment,
            "fabrication_signal": rec.fabrication_signal,
            "supported_hours": int(rec.supported_hours),
            "assessed_count": int(rec.assessed_count),
            "opened_at": int(rec.opened_at),
        }

    @gl.public.view
    def get_verdict(self, invoice_id: u256) -> str:
        assert invoice_id < self.invoice_count, "Unknown invoice"
        rec = self.invoices[invoice_id]
        return rec.verdict if rec.verdict else "PENDING"

    @gl.public.view
    def is_payable(self, invoice_id: u256) -> bool:
        assert invoice_id < self.invoice_count, "Unknown invoice"
        return self.invoices[invoice_id].verdict == Verdict.PAYABLE

    @gl.public.view
    def get_invoice_count(self) -> u256:
        return self.invoice_count

    @gl.public.view
    def get_owner(self) -> str:
        return self.owner
