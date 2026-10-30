# docs/history/

This directory retains the detailed historical changelog because code
comments still reference its change IDs. Obsolete point-in-time status
and implementation reports were removed to reduce clutter.

For the **current, canonical** project docs, see the root:

- `README.md`, `README_MASR.md` — current project overview
- `CHANGELOG.md` — current, single changelog (this directory's
  `FER3ON_FINAL_CHANGELOG.md` is the detailed historical version it
  summarizes)
- `PHASE_2_SAFETY_BOUNDARY.md` — **active** safety contract, still
  enforced and referenced by code (not archived — this one matters at
  runtime)
- `BACKTEST_VALIDITY_NOTICE.md` — **active** caveat about backtest data
  realism, still relevant (not archived)
- `certification_framework.md`, `certification_status.md` — **live,
  code-generated** files written by `certification/framework.py`, not
  static reports (not archived; moving them would just have them
  regenerate at root anyway)

## Retained history

- `FER3ON_FINAL_CHANGELOG.md` — detailed historical changelog with item IDs
  such as `[SLTP-1]` and `[EXPOSURE-1]` cited in source comments.
- `runtime_execution_map.md` — retained point-in-time runtime flow reference.
