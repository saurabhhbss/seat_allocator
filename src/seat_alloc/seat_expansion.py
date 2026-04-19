"""Expand programs + reservation config into individual SeatSlot rows.

This is the *optional* path — when the user provides a raw ``seat_matrix.csv``
with explicit per-bucket counts, this module is skipped and the CSV is loaded
directly.
"""

from __future__ import annotations

import math
from typing import Sequence

from .models import (
    Horizontal,
    Institute,
    Program,
    Programme,
    SeatSlot,
    SeatType,
    StateQuota,
    SupernumeraryKind,
    Vertical,
)
from .reservation_config import ReservationPolicy


def _largest_remainder_round(
    total: int, percentages: dict[str, float],
) -> dict[str, int]:
    """Allocate *total* seats across keys proportionally, summing to *total*."""
    raw = {k: total * p / 100.0 for k, p in percentages.items()}
    floors = {k: math.floor(v) for k, v in raw.items()}
    remainders = {k: raw[k] - floors[k] for k in raw}
    allocated = sum(floors.values())
    deficit = total - allocated
    for k in sorted(remainders, key=remainders.get, reverse=True):  # type: ignore[arg-type]
        if deficit <= 0:
            break
        floors[k] += 1
        deficit -= 1
    return floors


def expand(
    institutes: list[Institute],
    programs: list[Program],
    policy: ReservationPolicy,
) -> list[SeatSlot]:
    """Generate the full list of ``SeatSlot`` rows for the allocator."""
    inst_map = {i.code: i for i in institutes}
    slots: list[SeatSlot] = []

    for prog in programs:
        inst = inst_map.get(prog.institute_code)
        if inst is None:
            raise ValueError(
                f"Program {prog.program_code} references unknown institute "
                f"'{prog.institute_code}'."
            )

        for seat_type_enum, n_total in (
            (SeatType.GAS, prog.gas_seats),
            (SeatType.SFS, prog.sfs_seats),
        ):
            if n_total <= 0:
                continue

            mgmt_seats = 0
            if inst.type.value == "PRIVATE":
                mgmt_seats = round(prog.approved_intake * 0.15)
            centralized = n_total - min(mgmt_seats, n_total)
            if centralized <= 0:
                continue

            sq_pcts = {sq.quota.value: sq.percent for sq in policy.state_quotas}
            sq_counts = _largest_remainder_round(centralized, sq_pcts)

            rsq_total = sq_counts.get("RSQ", centralized)
            ors_total = sq_counts.get("ORS", 0)

            _expand_rsq(
                slots, prog, inst, seat_type_enum,
                rsq_total, policy,
            )

            if ors_total > 0:
                _expand_ors(slots, prog, inst, seat_type_enum, ors_total, policy)

        _expand_supernumerary(slots, prog, inst, policy)

    return slots


# ---------------------------------------------------------------------------
# RSQ expansion
# ---------------------------------------------------------------------------

def _expand_rsq(
    slots: list[SeatSlot],
    prog: Program,
    inst: Institute,
    seat_type: SeatType,
    rsq_total: int,
    policy: ReservationPolicy,
) -> None:
    vert_pcts = {v.vertical.value: v.percent for v in policy.verticals}
    vert_counts = _largest_remainder_round(rsq_total, vert_pcts)

    for vert_name, vert_seats in vert_counts.items():
        vert_enum = Vertical(vert_name)
        if vert_seats <= 0:
            continue

        if vert_enum == Vertical.ST and inst.is_tsp_area and policy.tsp:
            tsp_cfg = policy.tsp[0]
            tsp_seats = round(vert_seats * tsp_cfg.sub_quota_percent / 100)
            non_tsp_seats = vert_seats - tsp_seats
            _expand_horizontal(
                slots, prog, inst, seat_type, StateQuota.RSQ,
                vert_enum, "TSP", tsp_seats, policy,
            )
            _expand_horizontal(
                slots, prog, inst, seat_type, StateQuota.RSQ,
                vert_enum, "NON_TSP", non_tsp_seats, policy,
            )
        else:
            _expand_horizontal(
                slots, prog, inst, seat_type, StateQuota.RSQ,
                vert_enum, None, vert_seats, policy,
            )


# ---------------------------------------------------------------------------
# ORS expansion
# ---------------------------------------------------------------------------

def _expand_ors(
    slots: list[SeatSlot],
    prog: Program,
    inst: Institute,
    seat_type: SeatType,
    ors_total: int,
    policy: ReservationPolicy,
) -> None:
    _expand_horizontal(
        slots, prog, inst, seat_type, StateQuota.ORS,
        None, None, ors_total, policy,
    )


# ---------------------------------------------------------------------------
# Horizontal sub-quota carving
# ---------------------------------------------------------------------------

def _expand_horizontal(
    slots: list[SeatSlot],
    prog: Program,
    inst: Institute,
    seat_type: SeatType,
    state_quota: StateQuota,
    vertical: Vertical | None,
    tsp_subquota: str | None,
    bucket_seats: int,
    policy: ReservationPolicy,
) -> None:
    """Carve horizontal sub-quotas (WOMEN / PWD / EXS) out of a bucket."""
    remaining = bucket_seats

    for h in policy.horizontals:
        h_seats = round(bucket_seats * h.percent / 100)
        if h_seats <= 0:
            continue

        if h.axis == Horizontal.EXS and h.girls_sub_reservation > 0:
            girls_seats = round(h_seats * h.girls_sub_reservation / 100)
            boys_seats = h_seats - girls_seats
            if girls_seats > 0:
                slots.append(SeatSlot(
                    institute_code=prog.institute_code,
                    program_code=prog.program_code,
                    seat_type=seat_type,
                    state_quota=state_quota,
                    vertical=vertical,
                    horizontal=Horizontal.EXS_GIRLS,
                    tsp_subquota=tsp_subquota,
                    capacity=girls_seats,
                ))
                remaining -= girls_seats
            if boys_seats > 0:
                slots.append(SeatSlot(
                    institute_code=prog.institute_code,
                    program_code=prog.program_code,
                    seat_type=seat_type,
                    state_quota=state_quota,
                    vertical=vertical,
                    horizontal=Horizontal.EXS,
                    tsp_subquota=tsp_subquota,
                    capacity=boys_seats,
                ))
                remaining -= boys_seats
        else:
            slots.append(SeatSlot(
                institute_code=prog.institute_code,
                program_code=prog.program_code,
                seat_type=seat_type,
                state_quota=state_quota,
                vertical=vertical,
                horizontal=h.axis,
                tsp_subquota=tsp_subquota,
                capacity=h_seats,
            ))
            remaining -= h_seats

    if remaining > 0:
        slots.append(SeatSlot(
            institute_code=prog.institute_code,
            program_code=prog.program_code,
            seat_type=seat_type,
            state_quota=state_quota,
            vertical=vertical,
            horizontal=None,
            tsp_subquota=tsp_subquota,
            capacity=remaining,
        ))


# ---------------------------------------------------------------------------
# Supernumerary expansion
# ---------------------------------------------------------------------------

def _expand_supernumerary(
    slots: list[SeatSlot],
    prog: Program,
    inst: Institute,
    policy: ReservationPolicy,
) -> None:
    for sc in policy.supernumerary:
        if sc.percent <= 0:
            continue

        if sc.kind == SupernumeraryKind.TFWS and prog.programme == Programme.BARCH:
            continue
        if sc.kind == SupernumeraryKind.TFWS and prog.last_year_fill_pct < 50:
            continue

        cap = round(prog.approved_intake * sc.percent / 100)
        if cap <= 0:
            continue

        if sc.kind == SupernumeraryKind.FOREIGN_OCI:
            gulf_seats = round(cap / 3)
            other_seats = cap - gulf_seats
            slots.append(SeatSlot(
                institute_code=prog.institute_code,
                program_code=prog.program_code,
                capacity=gulf_seats,
                is_supernumerary=True,
                supernumerary_kind=SupernumeraryKind.FOREIGN_OCI,
                horizontal=Horizontal.WOMEN,  # placeholder tag for Gulf-child sub-res
            ))
            slots.append(SeatSlot(
                institute_code=prog.institute_code,
                program_code=prog.program_code,
                capacity=other_seats,
                is_supernumerary=True,
                supernumerary_kind=SupernumeraryKind.FOREIGN_OCI,
            ))
        else:
            slots.append(SeatSlot(
                institute_code=prog.institute_code,
                program_code=prog.program_code,
                capacity=cap,
                is_supernumerary=True,
                supernumerary_kind=sc.kind,
            ))
