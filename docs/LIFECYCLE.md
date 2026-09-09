# InvoiceTruth — Lifecycle

## States

```
                    assess_invoice()
open_invoice()      ┌──────────────────────────┐
     │              │  validators fetch URLs   │
     ▼              │  LLM → closed fields     │
  PENDING ─────────►│  run_nondet_unsafe binds │
     │              │  all 7 keys              │
     │              └──────────────────────────┘
     │                 │                │
     │   source        │                │  verdict derived
     │   unreachable   │                ▼
     │                 │           ASSESSED (terminal)
     │                 ▼         ├── PAYABLE
     │           UNRESOLVABLE    ├── INFLATED
     │           (retry          └── FABRICATED
     │            allowed)
     │                 │
     │                 │  assess_invoice() again
     │                 ▼
     │              PENDING-equivalent
     │              (reassessment)
```

- `PENDING`: opened, never assessed (or `UNRESOLVABLE` awaiting retry).
- `ASSESSED`: terminal verdict stored; further `assess_invoice` reverts
  (replay protection).
- `UNRESOLVABLE`: evidence unreachable, verdict `UNRESOLVED`;
  `assessed_count` still increments for audit, retry is allowed.

## Worked example

1. **Open.** Client calls:
   `open_invoice(rate_per_hour=10000, claimed_hours=40,`
   `claimed_amount=400000,`
   `timesheet_url="https://example.com/timesheets/inv-001.csv",`
   `repo_url="https://github.com/example/repo/commits?since=2026-08-01&until=2026-08-31")`
   → `invoice_id = 0`, status `PENDING`, URL digests sealed.
2. **Assess.** Anyone calls `assess_invoice(0)`. Validators fetch both
   URLs, the LLM returns:
   `{"commit_coverage": "FULL", "hours_alignment": "CONSISTENT",`
   `"amount_alignment": "EXACT", "fabrication_signal": "NONE",`
   `"supported_hours_seen": 40, "claimed_hours_seen": 40}`.
   All validators agree on the seven binding keys → consensus reached.
3. **Derive.** `expected = 40 * 10000 = 400000`, `delta = 0`,
   `within = True`. No fabrication, coverage `FULL`, alignment
   `CONSISTENT` → rule 8 → verdict `PAYABLE`, status `ASSESSED`.
4. **Consume.** An escrow contract calls `is_payable(0)` → `True` and
   releases funds. A later `assess_invoice(0)` reverts.

### Inflated variant

Same URLs, but the freelancer bills `claimed_amount=500000` while only
20h are supported: `expected = 200000`, `delta = 300000`,
`300000 * 10 > 200000` → outside tolerance, alignment `MAJOR_GAP` →
rule 5 → `INFLATED`.

### Fabricated variant

Repo URL shows no commits in the billing period (`commit_coverage =
NONE`): rule 2 → `FABRICATED` even if the timesheet claims 40h, because
a timesheet alone is insufficient evidence.
