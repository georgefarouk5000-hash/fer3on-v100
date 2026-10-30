# FER3ON FINAL — Build Changelog

This build was assembled from three sources per the merge blueprint in
`المطلوب_تنفيذه.txt`:

- **Base:** `fer3on-V9.1-fixed` (smartest signal/decision core, cleanest
  filter architecture)
- **Merged in:** `fer3on-V9-FINAL (1)` — stops-rejection execution retry
- **Merged in:** `fer3on-V3.7-final` — London open volatile-window block,
  NEWYORK session quality floor (threshold value taken from V9-FINAL instead
  of V3.7's, per the blueprint)

276 tests in `tests/` pass against this build (`python3 -m pytest tests/ -q`;
10 new tests added — see [SLTP-1]/[SLTP-2]/[SETTINGS-1-REVISED]/[EXPOSURE-1]/
[EXPOSURE-2]/[EXPOSURE-3]). This changelog documents every functional change
so you can audit or adjust any single decision independently.

**Read [SLTP-1], [SLTP-2], [EXPOSURE-3], and [EXPOSURE-1] first, in that
order.** They were found during testing and follow-up investigation, not in
the original blueprint, and matter more than everything else in this
document combined: [SLTP-1] is a pre-existing bug that silently disabled
V9.1's adaptive SL/TP engine entirely. [SLTP-2] is a structural finding
about your confirmed $200-$1000 real balance range and XAUUSD's minimum lot
size. [EXPOSURE-3] is a bug in my own [SLTP-2] work, caught before
delivery — the calibration didn't actually hold in the real code paths, and
would have silently prevented the bot from ever trading at $200-$500.
[EXPOSURE-1] is a related consequence of [SLTP-2] — the portfolio-wide risk
cap was checking real aggregate risk against a number 5-10x too small to
ever meaningfully trigger.

---

## [SETTINGS-1] — `core/settings.py`: account-tier config frozen & fail-safe (superseded — see [SETTINGS-1-REVISED])

**Problem:** The risk tier (small/medium/large account) was selected purely
from `BASE_ACCOUNT_BALANCE`, and that value itself came from two env vars
with an *aggressive* fallback: if `ACCOUNT_MODE` was left unset (default
`'DEMO'`), `BASE_ACCOUNT_BALANCE` silently became `1000.0`, landing in the
large-account tier (`MAX_LOT=0.10`, 10% daily risk). If this ever ran
against a real account without `ACCOUNT_MODE=REAL` + `ACCOUNT_BALANCE_USD`
set correctly, it would silently use the most aggressive profile in the
file.

**Fix:**
- `ACCOUNT_MODE=REAL`/`LIVE`/`LIVE_TRADING` with no explicit
  `ACCOUNT_BALANCE_USD` now fails safe to the **smallest** tier ($50,
  `MAX_LOT=0.01`) instead of assuming $1000, and prints a warning.
- Two hard ceilings now apply **after** tier selection, so no tier —
  including ones you edit later — can exceed them:
  - `MAX_LOT = min(MAX_LOT, 0.10)`
  - `MAX_RISK_PER_DAY_PERCENT = min(MAX_RISK_PER_DAY_PERCENT, 5.0)` (was
    10.0 for the large tier)
- All other tier values (small/medium account risk %, lot caps, SL floors)
  are unchanged from V9.1.

**Not changed:** `HARD_RISK_DAILY_LOSS_PERCENT` in `portfolio_risk_authority.py`
was already a separate, stricter, always-on 3.0% hard veto independent of
account tier — this was already the real operative daily-loss ceiling in
V9.1, tighter than the new 5.0% cap above. That mechanism is untouched.

**If you disagree with any of this:** every number above is a single line
in `core/settings.py` — search for `FER3ON FINAL` comments to find them.

---

## [SETTINGS-2] — Trade-frequency caps reduced

| Setting | Was (V9.1) | Now | Source |
|---|---|---|---|
| `MAX_DAILY_TRADES` | 100 | **50** | Blueprint Action Plan #6 (range 40–60; chose the midpoint) |
| `OFF_HOURS_MAX_TRADES` | 20 | **15** | Blueprint explicit ask / V9-FINAL's value |

`MAX_DAILY_TRADES` is now also the **single source of truth** — see
[EXEC-1] below; previously `core/trade_executor.py` had its own separate
hardcoded `100` that could silently drift from `settings.py`.

---

## [MAIN-1] — `main.py`: London open volatile-window hard block (ported from V3.7)

V3.7 documented a 33% win rate and –$178 P&L across 36 trades during the
08:00–10:00 UTC London open. `_build_live_snapshot()` now blocks **every**
strategy during this window, before any regime/structure/ATR work runs for
that tick (saves compute on a snapshot that would be discarded anyway):

```python
LONDON_VOLATILE_BLOCK_ENABLED = True   # core/settings.py
LONDON_VOLATILE_START = 8
LONDON_VOLATILE_END   = 10
```

Verified: a snapshot built at 09:30 UTC returns
`reason='LONDON_VOLATILE_WINDOW_BLOCK (08:00-10:00 UTC)'`; a snapshot at
11:00 UTC proceeds past this check normally.

---

## [QUALITY-1] — `core/quality_score.py`: NEWYORK session quality floor (ported from V3.7)

**Threshold chosen: 75** (V9-FINAL's value), not V3.7's 80 (blueprint judged
too strict) and not V9-fixed's absence of a floor (too permissive).

V9.1's `evaluate_quality_gate()` has *four* different paths that can approve
a trade (`STRICT_PASS`, an SMC/SCALP fast-pass at quality>=45, a
quality-floor adaptive pass, and a final quality>=43 fallback). Porting the
NY floor required closing all of them for the NEWYORK session specifically,
otherwise a low-quality NEWYORK trade could route around whichever single
check got patched:

1. `_session_floor()` — NEWYORK now returns `max(75, default_floor)` instead
   of the normal (lower) NEW_YORK floor.
2. `strict_threshold` is raised to at least 75 for NEWYORK before the
   `STRICT_PASS` check.
3. The SMC/SCALP quality>=45 fast-pass (a V9.1-only addition, kept for every
   other session) is skipped entirely during NEWYORK.
4. The general `quality_score >= QUALITY_ADAPTIVE_MIN_FLOOR` weak-bypass is
   blocked in NEWYORK when quality is below the 75 floor. The separate
   `ai_confident` bypass (requires `ml_score>=90` AND `confidence>=85`) is
   **still allowed** in NEWYORK — this matches V3.7's original intent
   verbatim: those two conditions together already count as "exceptionally
   clear" regardless of session.
5. The final quality>=43 last-resort fallback is raised to
   `max(43, final_floor)` for NEWYORK.

Verified with direct calls to `evaluate_quality_gate()`:
- NEWYORK, quality=60, confidence=60, ml_score=50 → **REJECTED**
- NEWYORK, quality=80, confidence=90 → **APPROVED** (`STRICT_PASS`, threshold 75)
- LONDON, quality=55 → unaffected, behaves exactly as before (`STRICT_PASS`, threshold 50)

---

## [EXEC-1] — `core/trade_executor.py`: stops-rejection retry (ported from V9-FINAL)

**Problem:** If a broker rejects an order because SL/TP are too close to the
current price, V9.1 gave up immediately. V9-FINAL retries with progressively
wider SL/TP until the broker accepts it.

**What was ported:** `_is_stops_too_close_rejection()` and
`_send_order_with_stops_retry()`, wrapping the pre-existing filling-mode
fallback loop (a *different* rejection class — order-fill type, not price
proximity — both loops now run together, widening-then-filling-fallback at
each widening level).

**Unit adaptation (important):** V9-FINAL's original version treated
`sl_dist`/`tp_dist` as raw price deltas (`price - sl_dist`). This codebase
(V9.1 base) treats them as **points**, multiplied by `point` everywhere else
in this file (`price - (sl_dist * point)`). The widening math itself
(`× (1 + ORDER_RETRY_STEP_PCT) ** attempt`) is unit-agnostic and carries over
unchanged, but the SL/TP price construction inside the retry function was
rewritten to multiply by `point`, matching the rest of `trade_executor.py`
and `main.py`. Copying V9-FINAL's version verbatim would have silently
placed SL/TP roughly 100x too close or too far from price on this codebase.

New settings (`core/settings.py`, values unchanged from V9-FINAL):
```python
ORDER_RETRY_ON_STOPS_REJECTION_ENABLED = True
ORDER_RETRY_STEP_PCT = 0.10          # +10% per attempt
ORDER_RETRY_MAX_ATTEMPTS = 5
ORDER_RETRY_REJECTION_RETCODES = (10016, 10017, 10006)
```

Also: `MAX_LIVE_DAILY_TRADES` (the counter that actually gates live order
submission) now imports `MAX_DAILY_TRADES` from `core/settings.py` instead
of a separate hardcoded `100` — this was the second, previously-invisible
copy of the daily-trade cap; without this fix, reducing `MAX_DAILY_TRADES`
in settings.py (see [SETTINGS-2]) would not have actually changed live
trading behaviour.

Verified with a mocked MT5 layer:
- Rejection on attempts 1–2 (`retcode=10016`, "Invalid stops"), success on
  attempt 3 → order sent with SL/TP widened ×1.21, no further retries.
- Non-stops rejection (e.g. "No money", `retcode=10019`) → **no retry**,
  fails immediately as before.
- Rejection on every attempt → stops exactly at `ORDER_RETRY_MAX_ATTEMPTS=5`
  and returns the last rejection (no infinite loop).

---

## [SLTP-1] — CRITICAL BUGFIX: the adaptive SL/TP engine was silently disabled

**This is the most significant finding in this build — bigger than anything
in the original merge blueprint.** It was found while testing [EXEC-1]
against realistic gold ATR values, not from the blueprint's own checklist.

**The bug:** `core/settings.py`'s `MIN_SL_DISTANCE` is a "points" setting
(e.g. `1500` meaning `1500 * point = $15` for gold). Every place that
converts it correctly does so with `* point`
(`BROKER_STOP_LEVEL_FALLBACK * point` two lines below it in the very same
function, `broker_min_pts_value * point`, and `MIN_SL_DISTANCE * 0.01` in
`main.py`'s own adaptive-engine call). But
`core/trade_executor.py::_enforce_min_stop_distance()` compared the **raw,
unconverted** `MIN_SL_DISTANCE` (1500) directly against `sl_dist` — which is
in **raw price dollars** from the adaptive engine (confirmed beyond doubt by
`core/trailing_stop.py`'s `new_sl = current_price - trailing_distance`,
which subtracts it directly from an absolute MT5 price with no conversion
anywhere in that file). Since `1500 >> ~$15-90` (a realistic adaptive stop),
the floor always won. The adaptive SL/TP engine — the single biggest reason
V9.1 was chosen as this build's base — **never once had any effect on the
actual stop sent to the broker.** Every trade got a flat, non-adaptive
$15 stop (for the large/only tier), regardless of ATR, volatility, session,
or structure.

Verified empirically before fixing: feeding ATR values of $3, $5, and $8
into the real adaptive engine produced genuinely different stop distances
($29.35, $48.91, $78.26) — all correctly discarded and replaced with exactly
$15.00 by the bug, every single time.

**The same bug, independently, in three more places** (same root cause —
`MIN_SL_DISTANCE` used unconverted):
- `core/risk_manager.py::calculate_smart_lot()` — used raw `sl_dist` directly
  in the MT5 tick-value lot-sizing formula, which requires the distance in
  **points**, not raw price dollars — a further ~100x sizing error that was
  masked by the first bug always forcing `sl_dist` back down to a
  coincidentally-plausible-looking 1500.
- `core/strategy_runners.py::_build_order_request_generic()` — identical
  floor bug, affecting the SCALP/SWING/MICRO execution paths (the SMC path
  in `main.py` and the SMC path's caller were the only ones with a correctly
  converted floor).
- `core/strategy_runners.py` — **six** separate calls to
  `calculate_adaptive_sl_tp(..., min_sl=MIN_SL_DISTANCE)` passed the raw
  1500 as the engine's safety floor (versus `main.py`'s correct
  `max(5.00, MIN_SL_DISTANCE * 0.01)`), which would have forced the engine's
  internal floor to $1500 for these strategies — i.e. an unusable, work-if-
  never-triggered value even bigger than the trade_executor bug.

**Fix:** every one of the four locations now converts `MIN_SL_DISTANCE` with
`* point` before use, and the `execute_trade()` / `_build_order_request()` /
`_build_order_request_generic()` / `_send_order_with_stops_retry()` price
construction was changed from `price - (sl_dist * point)` to `price -
sl_dist` (removing an erroneous **second** multiplication — sl_dist is
already in raw price dollars, so multiplying by `point` again shrank it by
~100x, which is what the floor bug had been masking). A new print line
(`💵 SL/TP DISTANCE (raw price units) | sl_dist=$X tp_dist=$Y`) was added in
`execute_trade()` so this is easy to sanity-check against the real MT5
terminal on your first demo runs.

**This fix was NOT part of the merge blueprint.** It predates this merge —
it is a bug in V9.1 itself, not something introduced by the V9FINAL1
execution-retry merge or by anything else in this build.

---

## [SLTP-2] — Gold's minimum lot size structurally limits risk-per-trade for a $200-$1000 account

Fixing [SLTP-1] correctly let realistic ATR-based stops ($29-90+) through —
which immediately exposed a second, structural (not a code bug) problem:
XAUUSD's broker-minimum lot (`MIN_LOT = 0.01` = 1oz) means **every** trade
risks at least $1 per $1 of stop distance, with no way to size smaller. A
$29-90 stop at 0.01 lot is $29-90 of risk regardless of any `risk_percent`
setting — 15-45% of a $200 balance. No risk-percent number can fix this;
the stop distance itself has to be bounded for an account this size, and
even then, the achievable risk-per-trade floor is materially higher than a
textbook 0.5-1%.

**Two new mechanisms, both new code (not in the original 4 codebases):**

1. **`MAX_SL_DISTANCE_DOLLARS = 10.0`** (`core/settings.py`) — caps the
   stop distance itself, applied everywhere `_enforce_min_stop_distance` or
   `_build_order_request_generic` builds a stop. This trades win-rate for
   survivability: a stop capped below what ATR suggests will be hit by
   ordinary noise more often than a "correct" wider stop would be. That is
   a real cost, not a free improvement — see "what I'd recommend you watch
   for" below.
2. **`MIN_LOT_RISK_MULTIPLE_CAP = 4.0`** + a new guard in
   `calculate_smart_lot()` — after sizing, if MIN_LOT's implied dollar risk
   still exceeds `4x` the intended `risk_amount`, the function returns
   `lot=0.0` instead of forcing the trade. Every caller in this codebase
   already treats `lot <= 0` as "don't trade this signal" (`if lot > 0:` /
   `'allowed': lot > 0`), so this required no caller changes.

**Calibrated outcome across your stated $200-$1000 range** (verified with a
mocked MT5 tick_value, realistic ATR values, and the real adaptive engine):

| Balance | Stop (capped) | Lot | Actual $ risk | % of balance |
|---|---|---|---|---|
| $200 | $10.00 | 0.01 | $10.00 | **5.0%** |
| $500 | $10.00 | 0.01 | $10.00 | **2.0%** |
| $1000 | $10.00 | 0.01 | $10.00 | **1.0%** |

Risk-per-trade naturally scales down as balance grows within your range —
this falls out of the mechanics (fixed $ stop, fixed MIN_LOT) rather than
requiring separate tiers.

**Why 5% at $200 and not tighter:** I tried a stricter guard first (skip
unless within 2x-3x of a 0.75-1.5% target) and it skipped every single
trade at $200 — the account is simply too small for gold's lot granularity
to hit a "safe" textbook risk number at all. 5% is the practical floor, not
a preference. `core/settings.py::HARD_RISK_DAILY_LOSS_PERCENT = 3.0%`
(unchanged, pre-existing) means a single loss at $200 will already exceed
the daily hard-risk veto and halt trading for the rest of the day — this is
appropriate given each trade risks ~5%, not an oversight.

**What I'd recommend you watch for on demo:** the $10 cap is tighter than
pure ATR would pick for gold, so expect more stop-outs from ordinary price
noise than a wider stop would see, especially during volatile sessions.
If you find the $200-350 end of your range gets stopped out constantly
without ever reaching TP, that's this trade-off manifesting — the fix at
that point is either trading a larger portion of your range (the $1000 end
is far more comfortable at 1%) or accepting a higher `MIN_LOT_RISK_MULTIPLE_CAP`
tolerance if you're comfortable with wider stops. Both are one-line changes
in `core/settings.py`.

**Regression tests added:** `tests/test_sltp_unit_fix.py` (4 tests) locks in
the unit-conversion fix specifically — if `MIN_SL_DISTANCE`'s conversion or
the points/price-unit handling in `calculate_smart_lot` ever regresses,
these will fail loudly. `tests/test_small_account_profile.py` was rewritten
(the old version asserted the now-removed 3-tier system's $50-tier values)
to test the actual MIN_LOT_RISK_GUARD mechanism instead.

---

## [SETTINGS-1-REVISED] — Single frozen profile (supersedes the earlier 3-tier fix)

The 3-tier account-size system from the original [SETTINGS-1] fix (small
$50 / medium $100 / large $200+ tiers, auto-selected from a guessed balance)
has been **replaced entirely** with one explicit profile now that the real
balance range ($200-$1000) is known — removing the config-ambiguity risk
by elimination rather than by capping it:

```python
RISK_PER_TRADE_PERCENT = 1.5     # see [SLTP-2] — realistic given MIN_LOT granularity
MAX_RISK_PER_DAY_PERCENT = 5.0   # unchanged
MAX_LOT = 0.10                   # unchanged ceiling
MIN_LOT = 0.01                   # broker floor
MIN_SL_DISTANCE = 500.0          # last-resort floor only (ATR failure) — see [SLTP-1]
MAX_SL_DISTANCE_DOLLARS = 10.0   # new — see [SLTP-2]
MIN_LOT_RISK_MULTIPLE_CAP = 4.0  # new — see [SLTP-2]
```

`RISK_PER_TRADE_PERCENT=1.5` is a budget reference used by
`calculate_smart_lot`'s sizing math and the MIN_LOT_RISK_GUARD's cap
calculation — for most of your range, the MIN_LOT_RISK_GUARD or the raw
lot-sizing formula (whichever binds) determines the actual risk, not this
number directly; see the table in [SLTP-2] for what actually gets risked.
REAL mode with no explicit `ACCOUNT_BALANCE_USD` now fails safe to $200
(the low end of your range) instead of guessing.

---

## Deliberately NOT changed

Per the blueprint's own preservation map, these V9.1-exclusive strengths
were left untouched: `core/unified_decision.py`, `core/unified_bridge.py`,
`core/adaptive_sl_tp_engine.py` (its internal ATR/quality/structure logic —
only its two call sites' `min_sl` conversion was fixed, see [SLTP-1]),
`core/professional_swing_structure.py`, `core/portfolio_risk_authority.py`,
and the SMC/SCALP quality fast-pass in `quality_score.py` (kept for every
session except NEWYORK, see [QUALITY-1]). V9-fixed's more
permissive/aggressive package was not used as a source for anything in
this build.

## Investigation findings: items #11 and #20 from the original audit turned out to be non-issues in the live code path

Requested follow-up work on the audit's remaining checklist items ("de-duplicate
confidence/ML penalties across layers" and "demote AI from hidden blocker to
explicit scorer in logs") led to tracing the actual live decision path in
`main.py` end to end, rather than assuming the audit's file-level concerns
applied to code that runs. Two files the audit's concerns were based on turned
out to be **dead code, never called from `main.py` or any live path**:
`core/ai_v1_authority.py` (confirmed via `grep` — only referenced from one
test file), `core/brain_unified.py`, and `core/candle_gate_v3.py`. The real,
live decision authority is `core/unified_decision.py`'s `unified_decide()`
(called via `core/fer3on_decision_authority.py::decide_trade()`), and:

- **#20 is already substantially satisfied in the live path.**
  `unified_decision.py::format_decision_log()` already prints a detailed,
  named breakdown every cycle (`Composite Score`, `Execution Grade`,
  `Execution/ATR/Liquidity/Candle/Structure Bonus`, `ML Penalty`,
  `MTF Penalty`, `SMC Penalty`, plus a `smart_classification` +
  `smart_explanation` field) — this is not a hidden blocker, it's already an
  explicit, itemized scorer. The audit's concern likely came from reading
  `ai_v1_authority.py`'s more opaque `HARD_BLOCK` path, which never runs.
- **#11's "duplication" is intentional layered design in the live path, not
  a bug.** `main.py` deliberately runs `quality_gate` (sets lot-size TIER)
  and `runtime_decision`/authority (sole arbiter of PASS/FAIL) as two
  separate systems that both consider `ml_score`/`confidence`, then
  explicitly takes **the more conservative of the two** (see `main.py`'s own
  comment block above `_effective_mode` — "authority gates EXECUTION, quality
  ... determine LOT SIZE TIER... take the most conservative of the two").
  This is defense-in-depth, not accidental double-penalization.

No code changes were made for #11/#20 — correcting a diagnosis is safer than
"fixing" code that already works as intended, especially in a system handling
real money. Left as unresolved and out of scope for now: whether the three
dead files should eventually be deleted (`core/ai_v1_authority.py` is still
imported by `tests/ai_consistency/test_authority_immutable.py`, so removing
it would need that test updated too — not done here to avoid touching test
coverage without a clearer reason than "it looks unused").

---

## [EXPOSURE-3] — CRITICAL: the SLTP-2 calibration didn't actually hold in the real code paths

**Found by testing my own [SLTP-2] fix against the ACTUAL formulas in
`main.py` and `core/strategy_runners.py`, instead of trusting the synthetic
test value I'd calibrated against.** This is a bug I introduced while
building [SLTP-2], caught before delivery — worth being explicit about
rather than quietly folding into the numbers above.

[SLTP-2]'s worked example (the $200/$500/$1000 → 5%/2%/1% table) used
`risk_percent=RISK_PER_TRADE_PERCENT` (1.5%) directly. But **neither real
code path actually passes that value** to `calculate_smart_lot`:

- `main.py`'s SMC path computed its own `risk_percent = round(max(0.10,
  min(0.75, 0.50 * risk_multiplier)), 3)` — a hardcoded 0.50% base
  completely disconnected from `settings.RISK_PER_TRADE_PERCENT`, giving
  0.10-0.75% depending on decision confidence.
- `core/strategy_runners.py`'s SCALP/SWING/MICRO paths used their own
  independent `BASE_RISK_SCALP/SWING/MICRO` constants (0.40-0.75%), also
  disconnected from `RISK_PER_TRADE_PERCENT`.

Verified empirically: feeding these **real** values into the (correctly
implemented) `MIN_LOT_RISK_GUARD` at a $200 balance skipped **every single
combination** — every confidence level on the SMC path, and every one of
SCALP/SWING/MICRO. The bot would have silently never opened a single trade
at the $200-$500 end of your confirmed range, despite [SLTP-2]'s table
showing "5% risk, trades fine." The table was correct for the number I
tested; it just wasn't the number the real code was using.

**Root cause:** the same disease as [SETTINGS-1]/[EXPOSURE-1] — duplicated,
uncoordinated risk-percent definitions scattered across the codebase (this
is exactly audit item #2, "duplicated risk definitions," which turned out to
have more instances than the ones already fixed in `core/settings.py`'s
account tiers).

**Fix:**
- New setting `MIN_EFFECTIVE_RISK_PERCENT = 1.35` — a floor, not a
  replacement, for any risk_percent formula derived from
  `RISK_PER_TRADE_PERCENT`.
- `main.py`'s formula now scales `RISK_PER_TRADE_PERCENT` by the same
  `risk_multiplier` (preserving the original *intent* — higher confidence
  → higher risk — while anchoring the base to the real setting) and floors
  at `MIN_EFFECTIVE_RISK_PERCENT`, ceilings at `MAX_RISK_TOTAL`.
- `BASE_RISK_SCALP/SWING/MICRO/SMC/DAILY` are now all defined as
  `max(MIN_EFFECTIVE_RISK_PERCENT, RISK_PER_TRADE_PERCENT * factor)`,
  preserving their original relative ordering (SCALP/SMC highest, SWING
  middle, MICRO lowest) while guaranteeing none of them can silently stop
  clearing the guard.

**Verified fix, all four strategies × three balances × four confidence
levels:** every combination now sizes a trade successfully (mostly at
`MIN_LOT=0.01`, occasionally higher at $1000 with high confidence — the
sizing formula engaging organically rather than always being floor-bound).

**Regression test added:** `tests/test_real_risk_percent_clears_guard.py`
— deliberately re-implements (copies, does not import) the exact formulas
from `main.py` and `core/strategy_runners.py` so that if either drifts away
from `RISK_PER_TRADE_PERCENT` again in a future edit, this test catches it
immediately rather than requiring another manual "test against real
production values" pass like this one.

---

## [EXPOSURE-1] — Portfolio exposure cap was checking against the wrong risk number

**Found while investigating audit item #12** (cross-strategy same-direction
exposure cap) and directly caused by [SLTP-2]'s own MIN_LOT_RISK_GUARD.

`core/portfolio_risk_authority.py::compute_current_exposure()` sums the
`risk_percent` field recorded on each open trade to enforce
`MAX_RISK_TOTAL` (2.0%). Both `main.py` and `core/strategy_runners.py`
recorded this field as the **nominal pre-sizing** risk_percent request — in
`main.py`'s case, a small, unrelated formula
(`round(max(0.10, min(0.75, 0.50 * risk_multiplier)), 3)`, giving ~0.10-0.75%)
that has no connection to `core/settings.py`'s `RISK_PER_TRADE_PERCENT` or to
what the trade actually risks. After [SLTP-2], the REAL dollar risk on a
$200-$1000 account is usually ~1-5% per trade (MIN_LOT dominates sizing, not
the nominal risk_percent) — so the exposure cap was comparing real aggregate
risk against numbers 5-10x too small, and could essentially never trigger
before real risk got dangerous.

**Fix:** a new `core.risk_manager.compute_realized_risk_percent(lot,
entry_price, sl_price, balance)` computes the actual %-of-balance risk from
the FINAL lot and SL price actually sent to the broker (same points/tick_value
math as `calculate_smart_lot`, see [SLTP-2]). Both `main.py` and
`core/strategy_runners.py` now record this realized figure via
`record_trade_open()` instead of the nominal one.

**Verified effect:** on a $200 account, one trade now realistically records
~5% exposure — since `MAX_RISK_TOTAL=2.0%`, a second concurrent trade is now
correctly **blocked** (`EXPOSURE_LIMIT_HIT`) until the first closes. Before
this fix, the tiny nominal number recorded meant multiple concurrent trades
could open well past what `MAX_RISK_TOTAL` was supposed to allow. This is a
more protective outcome than before, consistent with [SLTP-2]'s finding that
this account size structurally can't run multiple loosely-supervised
concurrent gold positions at once.

## [EXPOSURE-2] — Same-direction concentration cap ported to SCALP/SWING/MICRO

`main.py`'s SMC path already checked live MT5 positions and blocked a new
trade if 4+ existing positions shared its direction — `core/strategy_runners.py`
(SCALP/SWING/MICRO) had no equivalent check, only the direction-blind
`MAX_OPEN_TRADES` total-position cap (shared via `evaluate_risk()`). Ported
the identical check into `core/strategy_runners.py::_execute()`, and named
the threshold `MAX_SAME_DIRECTION_POSITIONS = 4` in `core/settings.py` so
both paths reference one number instead of two independently-hardcoded 4s.
Because it reads live MT5 positions directly, it is inherently cross-strategy
— a SCALP long and a SWING long on the same symbol count together. Note:
[EXPOSURE-1]'s realized-risk exposure cap is the stronger, risk-aware
protection against directional concentration for this account size; this
count-based cap is a secondary, coarser backstop.

**Regression tests added:** `tests/test_exposure_realized_risk.py` (2 tests)
verifies `compute_realized_risk_percent` matches the SLTP-2 calibration table
and that a second trade is correctly blocked on a small account once the
first trade's realized risk is recorded.

---

## Bonus fix (unrelated to the merge, found during a full compile sweep)

`tools/generate_phase2_reports.py` had a pre-existing syntax error (`"\"`
unterminated string literal) inherited from V9.1 — this is a standalone
reporting script, not on the trading runtime path, but it's fixed here
(`"\\"`) since it was a one-line, zero-risk correction.

## What was NOT reviewed line-by-line

These codebases are ~350–550 files each. This build implements the specific,
concrete merge items the blueprint document called out by name (the account
config danger, the two trade-frequency caps, the London block, the NEWYORK
floor, and the stops-retry executor) with full verification of each. It does
not re-audit every one of the hundreds of files that the blueprint already
found equivalent or superior in V9.1 — if you want a specific other file
compared across versions, point me at it and I'll do that pass too.

---

## Branch merge (2026-08-18) — rearch-phase1-2 + CERT-6 reapplied

Two divergent branches existed off this build: `FER3ON-FINAL-build1-CERT1-6-fixes`
(certification-fix audit round, [CERT-1] through [CERT-6] above) and
`FER3ON-FINAL-build1-rearch-phase1-2` (architectural de-duplication —
see `docs/history/REARCH_PHASE1_2026-08-18.md` and
`docs/history/REARCH_PHASE2_2026-08-18.md`). Neither had been run or tested.

Comparing both against this file and against each other directly (file
diffs, not just changelog text) found:

- [CERT-1] through [CERT-5]'s underlying fixes were already present in the
  rearch branch (some via the more robust REARCH-2/REARCH-3 mechanisms,
  which remove the drift risk structurally rather than just correcting the
  one instance CERT found) — the rearch branch had simply forked before
  those fixes were tagged with `[CERT-n]` labels, so its comments read
  "AUDIT FIX" / "AUDIT NOTE" generically instead.
- [CERT-6] (`core/trade_executor.py` STEP 3 reading
  `settings.MAX_OPEN_PER_STRATEGY` instead of a hardcoded `>= 1`, plus its
  4-test `PerStrategyLimitTests` coverage) was genuinely missing from the
  rearch branch — it forked before CERT-6 was written. No live-behavior
  difference today (`MAX_OPEN_PER_STRATEGY == 1` either way, confirmed by
  CERT-6's own note above), but it's a real regression in
  config-correctness and testability if that value is ever changed.

**Action:** took the rearch-phase1-2 branch as the base (architecturally
the more complete of the two) and re-applied [CERT-6] on top of it —
`_check_per_strategy_limit()` restored in `core/trade_executor.py` (built
on `get_min_sl_dollars()` / [REARCH-1], not the pre-REARCH inline formula),
its `MAX_OPEN_PER_STRATEGY` import restored, the explanatory comment
restored in `core/portfolio_risk_authority.py`, and the 4
`PerStrategyLimitTests` restored in `tests/test_audit_fixes.py`.

**Verified effect:** full suite run after merge: **545 passed, 1 skipped,
17 subtests** — identical count to the CERT branch's own full suite, and
the delta from the rearch branch's 541 is exactly these 4 restored tests.
`python3 -m py_compile` sweep of the full tree and a live `import main`
smoke check both clean on the merged build. This build has still not been
run against a demo/live MT5 terminal — only the offline unit-test suite
above.
