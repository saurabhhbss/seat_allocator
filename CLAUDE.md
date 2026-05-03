# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a **REAP-2026 seat allocation simulator** — a Python implementation of the Rajasthan Engineering Admission Process. It matches students to engineering college seats using a choice-first Gale-Shapley algorithm with complex reservation rules (caste-based verticals, gender/disability/ex-servicemen horizontals, geographic quotas, supernumerary categories, and progressive multi-round merging).

## Commands

```bash
# Install (editable mode)
pip install -e .

# Launch Streamlit UI
seat ui
# or
./run.sh

# Headless batch run
seat run --data data --out results

# Quick verification (places 40 sample students)
python demo.py

# Scenario demonstrations
python examples.py
```

No test framework is configured; verification is done via `demo.py` (expects 100% placement rate on sample data).

## Architecture

The engine lives in `src/seat_alloc/` with a strict data flow:

```
CSV files (data/)
    → io_csv.py          (load + validate all inputs)
    → reservation_config.py + category_priority.py   (policy)
    → eligibility.py     (build per-student CandidateSlot lists)
    → allocator.py       (choice-first Gale-Shapley, per-round)
    → rounds.py          (orchestrate 11 rounds, call merge/slide)
    → internal_sliding.py / withdrawal.py  (between-round adjustments)
    → reports.py         (cutoffs, vacancies, allocations, traces)
```

**Key design decisions:**

- **models.py** defines all domain enums and Pydantic dataclasses. Understand `SeatSlot`, `Allocation`, `SimulationState` before touching anything else.
- **allocator.py** is the core. A bounded-heap per `SeatSlot` tracks occupants by rank; displaced students re-enter from their next untried slot.
- **rounds.py** `run_simulation()` is the entry point for a full run. It maintains `SimulationState` and drives the round loop. Progressive merging (`merge_horizontal()` in `allocator.py`) happens after round 1 (WOMEN) and round 2 (PWD, EXS).
- **eligibility.py** enforces domain rules about who can propose to which category (e.g., WOMEN seats only for female students, PWD requires `is_pwd`, TSP requires `is_tsp_area_resident`).
- **category_priority.py** + `category_priority.csv` drive **merit-first** behavior: SC-ranked students try GEN seats before SC seats.
- **reservation_config.py** holds all percentage policies (SC 16%, ST 12%, WOMEN 30%, etc.) with built-in REAP defaults used when CSV overrides are absent.
- **seat_expansion.py** is optional — generates `seat_matrix.csv` from higher-level program definitions when you don't want to hand-author the full matrix.
- **ui/app.py** is a 5-step Streamlit wizard (load → edit → policy → run → results). It calls the same engine as the CLI.
- **cli.py** defines two Click commands: `seat ui` and `seat run`.

## Input CSV Schema

All policy is CSV-driven; no code changes needed to adjust quotas or rounds.

| File | Required | Purpose |
|------|----------|---------|
| `data/seat_matrix.csv` | Yes | Per-bucket seat capacities (institute × program × seat_type × state_quota × vertical × horizontal × tsp) |
| `data/students.csv` | Yes | Student profile (category, gender, PWD, EXS code, domicile, income, etc.) |
| `data/ranks.csv` | Yes | Pre-computed ranks per student per category (multiple rows per student) |
| `data/choices.csv` | Yes | Ordered preferences (application_no, preference_order, institute, program) |
| `data/rounds_config_betech.csv` | No | 11-round schedule for B.E./B.Tech with merge and mode per round |
| `data/category_priority.csv` | No | Merit-first priority order per vertical (default: reserved categories try GEN first) |

## Round Modes

Five modes are used in `rounds_config_betech.csv`:
- `mock` — trial run, no commitment
- `fresh` — new allocation cycle
- `upward` — reported students can move to better choices
- `sliding` — institute-internal vertical sliding
- `spot` — direct + management quota

## Extending the System

- **New supernumerary category**: Add to `SupernumeraryKind` enum in `models.py`, update eligibility check in `eligibility.py`, and add to `supernumerary.csv` or its defaults.
- **New reservation percentage**: Edit `data/reservation_config.csv` or the hardcoded defaults in `reservation_config.py`.
- **New round**: Add a row to `data/rounds_config_betech.csv` — no code change required.
- **Change merit-first order**: Edit `data/category_priority.csv`.
