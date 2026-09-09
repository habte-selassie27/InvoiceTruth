# InvoiceTruth — Design

## Trust model

1. **Client seals evidence at open time.** `open_invoice` stores
   `rate_per_hour`, `claimed_hours`, `claimed_amount`, `timesheet_url`,
   and `repo_url` immutably, plus `SHA-256(url)` digests for both URLs.
   `assess_invoice` re-verifies the digests and fails closed on mismatch,
   so neither the opener nor a later caller can swap sources.
2. **Validators fetch, callers don't supply text.** All evidence enters
   through `gl.nondet.web.get` inside the nondet boundary (`leader_fn`).
   Caller-supplied strings are never treated as evidence.
3. **LLM is scope-limited.** The model returns only closed observations —
   four enum fields plus two integer fields. It never outputs
   `PAYABLE` / `INFLATED` / `FABRICATED` directly.
4. **Contract derives the verdict deterministically.** `derive_verdict`
   maps the seven bound fields to a verdict with integer math only.
   `amount_alignment` from the model is stored for audit, but the 10%
   tolerance is recomputed from `supported_hours * rate_per_hour`, so a
   dishonest model label cannot force `PAYABLE`.
5. **No custody, no admin override.** The contract holds no tokens and the
   owner has no power over individual verdicts. The registry is bounded
   (`max_invoices = 500`).

## Equivalence check

Each validator independently re-runs `leader_fn` (fetch both URLs, run
the audit prompt, normalize the JSON). `validator_fn` accepts the
leader's result only if all seven binding keys match exactly:

- `source_reachable`
- `commit_coverage` (`FULL` | `PARTIAL` | `NONE`)
- `hours_alignment` (`CONSISTENT` | `MINOR_GAP` | `MAJOR_GAP` | `UNVERIFIABLE`)
- `amount_alignment` (`EXACT` | `TOLERABLE` | `OVERSTATED` | `UNDERSTATED`)
- `fabrication_signal` (`NONE` | `SUSPECTED` | `CONFIRMED`)
- `supported_hours_seen` (integer)
- `claimed_hours_seen` (integer)

Free-form text is never compared or stored. Content hashes are omitted
from consensus: live repos may legitimately differ between fetches, so
the semantic fields — not byte equality — are the binding signal.
