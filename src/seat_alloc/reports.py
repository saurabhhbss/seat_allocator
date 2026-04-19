"""Reporting utilities — cutoffs, per-round tables, vacancy reports."""

from __future__ import annotations

import pandas as pd

from .models import Allocation, SeatSlot
from .rounds import RoundResult, SimulationState


def allocation_table(allocs: list[Allocation]) -> pd.DataFrame:
    """Flat DataFrame of allocations for display / export."""
    if not allocs:
        return pd.DataFrame()
    return pd.DataFrame([a.model_dump() for a in allocs])


def per_round_summary(state: SimulationState) -> pd.DataFrame:
    """One row per round with counts."""
    rows = []
    for rr in state.round_results:
        rows.append({
            "round_no": rr.round_no,
            "name": rr.name,
            "mode": rr.mode.value,
            "allocated": len(rr.allocations),
            "unplaced": len(rr.unplaced),
            "merge_events": "; ".join(rr.merge_events) if rr.merge_events else "",
        })
    return pd.DataFrame(rows)


def cutoff_table(state: SimulationState) -> pd.DataFrame:
    """Opening and closing ranks per (institute, program, category) per round.

    The opening rank is the *best* (lowest) rank admitted;
    the closing rank is the *worst* (highest) rank admitted.
    """
    from collections import defaultdict

    data: dict[tuple, dict[str, int]] = defaultdict(lambda: {"opening": float("inf"), "closing": 0})

    for rr in state.round_results:
        for alloc in rr.allocations:
            key = (
                rr.round_no,
                alloc.institute_code,
                alloc.program_code,
                alloc.category_token,
            )
            rank = state.ranks.get(alloc.application_no, {}).get(alloc.category_token)
            if rank is None:
                continue
            entry = data[key]
            entry["opening"] = min(entry["opening"], rank)
            entry["closing"] = max(entry["closing"], rank)

    rows = []
    for (rnd, inst, prog, cat), ranks in sorted(data.items()):
        rows.append({
            "round_no": rnd,
            "institute_code": inst,
            "program_code": prog,
            "category": cat,
            "opening_rank": ranks["opening"] if ranks["opening"] != float("inf") else None,
            "closing_rank": ranks["closing"] if ranks["closing"] > 0 else None,
        })
    return pd.DataFrame(rows)


def vacancy_table(
    seat_slots: list[SeatSlot],
    allocations: dict[str, Allocation],
) -> pd.DataFrame:
    """Show per-bucket capacity vs filled vs vacant."""
    from collections import Counter

    filled_counts: Counter[tuple] = Counter()
    for alloc in allocations.values():
        key = (
            alloc.institute_code,
            alloc.program_code,
            alloc.category_token,
        )
        filled_counts[key] += 1

    rows = []
    for slot in seat_slots:
        cat = slot.category_token()
        key = (slot.institute_code, slot.program_code, cat)
        filled = filled_counts.get(key, 0)
        rows.append({
            "institute_code": slot.institute_code,
            "program_code": slot.program_code,
            "seat_type": slot.seat_type.value if slot.seat_type else "",
            "state_quota": slot.state_quota.value if slot.state_quota else "",
            "vertical": slot.vertical.value if slot.vertical else "",
            "horizontal": slot.horizontal.value if slot.horizontal else "",
            "tsp_subquota": slot.tsp_subquota or "",
            "supernumerary": slot.supernumerary_kind.value if slot.supernumerary_kind else "",
            "category": cat,
            "capacity": slot.capacity,
            "filled": filled,
            "vacant": max(0, slot.capacity - filled),
        })
    return pd.DataFrame(rows)


def student_trace(
    app_no: str,
    state: SimulationState,
) -> pd.DataFrame:
    """Per-round trace for a single student — what happened in each round."""
    rows = []
    for rr in state.round_results:
        matched = [a for a in rr.allocations if a.application_no == app_no]
        if matched:
            a = matched[0]
            rows.append({
                "round_no": rr.round_no,
                "round_name": rr.name,
                "status": "allocated",
                "institute_code": a.institute_code,
                "program_code": a.program_code,
                "category": a.category_token,
            })
        elif app_no in rr.unplaced:
            rows.append({
                "round_no": rr.round_no,
                "round_name": rr.name,
                "status": "unplaced",
                "institute_code": "",
                "program_code": "",
                "category": "",
            })
    student = state.student_map.get(app_no)
    final = state.current_allocations.get(app_no)
    if final:
        rows.append({
            "round_no": 999,
            "round_name": "FINAL",
            "status": "final_allocation",
            "institute_code": final.institute_code,
            "program_code": final.program_code,
            "category": final.category_token,
        })
    return pd.DataFrame(rows)
