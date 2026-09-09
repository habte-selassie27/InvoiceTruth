"""
InvoiceTruth — Direct-mode test suite
Tests cover:
  1. Happy path: PAYABLE verdict
  2. Inflated hours: INFLATED verdict
  3. No commits: FABRICATED verdict
  4. Confirmed fabrication: FABRICATED verdict
  5. Unreachable source: UNRESOLVABLE, then retry
  6. Replay protection on terminal verdict
  7. Self-challenge: open_invoice parameter validation
  8. Integer math tolerance boundary (exact 10%)
  9. Integer math tolerance boundary (just over 10%)
 10. is_payable predicate
 11. get_verdict consumer method
 12. Distinct URL enforcement
 13. Zero rate rejected
 14. Zero hours rejected
 15. Registry cap enforcement (conceptual)
 16. Model cannot bypass INFLATED via amount_alignment label
 17. URL digest commitment round-trips
"""

import pytest

from contract.invoice_truth import (
    derive_verdict,
    validate_open_params,
    url_digest,
)


class TestVerdictDerivation:

    def test_01_payable_full_coverage_exact_amount(self):
        verdict = derive_verdict(
            source_reachable=True,
            commit_coverage="FULL",
            hours_alignment="CONSISTENT",
            amount_alignment="EXACT",
            fabrication_signal="NONE",
            supported_hours=40,
            rate_per_hour=10000,
            claimed_amount=400000,
        )
        assert verdict == "PAYABLE"

    def test_02_payable_partial_coverage_tolerable(self):
        verdict = derive_verdict(
            source_reachable=True,
            commit_coverage="PARTIAL",
            hours_alignment="MINOR_GAP",
            amount_alignment="TOLERABLE",
            fabrication_signal="NONE",
            supported_hours=38,
            rate_per_hour=10000,
            claimed_amount=400000,
        )
        assert verdict == "PAYABLE"

    def test_03_inflated_major_gap(self):
        verdict = derive_verdict(
            source_reachable=True,
            commit_coverage="PARTIAL",
            hours_alignment="MAJOR_GAP",
            amount_alignment="OVERSTATED",
            fabrication_signal="NONE",
            supported_hours=20,
            rate_per_hour=10000,
            claimed_amount=400000,
        )
        assert verdict == "INFLATED"

    def test_04_inflated_amount_overstated_beyond_tolerance(self):
        verdict = derive_verdict(
            source_reachable=True,
            commit_coverage="FULL",
            hours_alignment="CONSISTENT",
            amount_alignment="OVERSTATED",
            fabrication_signal="NONE",
            supported_hours=40,
            rate_per_hour=10000,
            claimed_amount=500000,
        )
        assert verdict == "INFLATED"
