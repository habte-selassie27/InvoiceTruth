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

## Priority rule table

Evaluated top-down; the first matching rule decides.

| Priority | Condition | Verdict |
|---|---|---|
| 0 | `source_reachable == False` | `UNRESOLVED` (status `UNRESOLVABLE`, retry allowed) |
| 1 | `fabrication_signal == CONFIRMED` | `FABRICATED` |
| 2 | `commit_coverage == NONE` (timesheet alone is insufficient) | `FABRICATED` |
| 3 | `SUSPECTED` + `MAJOR_GAP` | `FABRICATED` |
| 4 | `supported_hours * rate == 0` | `FABRICATED` |
| 5 | `hours_alignment == MAJOR_GAP` | `INFLATED` |
| 6 | over-billed beyond tolerance (model label **or** recomputed math) | `INFLATED` |
| 7 | (`MINOR_GAP` or `SUSPECTED`) and outside tolerance | `INFLATED` |
| 8 | all checks pass | `PAYABLE` |

Under-billing (`claimed < expected`) with `CONSISTENT` alignment and no
suspicion stays `PAYABLE`: the freelancer simply claimed less than the
evidence supports.

## Integer-only math

All money is in the smallest currency unit; hours are integers.

```
expected = supported_hours * rate_per_hour
delta    = |claimed_amount - expected|
within   = (delta * 10) <= expected        # delta <= 10% without division
over     = claimed_amount > expected and not within
```

Boundary behavior (rate `10000`, 40h supported, expected `400000`):

- `claimed = 440000` → `delta * 10 = 400000 <= 400000` → within → `PAYABLE`
- `claimed = 440001` → `delta * 10 = 400010 > 400000` → outside → `INFLATED`
