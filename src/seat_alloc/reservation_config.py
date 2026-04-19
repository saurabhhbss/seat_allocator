"""Load, validate, and provide REAP-default reservation configuration.

Wraps all the config CSVs into a single ``ReservationPolicy`` object that
the seat-expansion and allocator modules consume.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .io_csv import (
    load_exs_priorities,
    load_horizontal_reservations,
    load_state_quota_configs,
    load_supernumerary_configs,
    load_tsp_config,
    load_vertical_reservations,
)
from .models import (
    ExsCode,
    ExsPriority,
    Horizontal,
    HorizontalReservation,
    StateQuota,
    StateQuotaConfig,
    SupernumeraryConfig,
    SupernumeraryKind,
    TspConfig,
    Vertical,
    VerticalReservation,
)


@dataclass
class ReservationPolicy:
    """All reservation configuration in one object."""

    verticals: list[VerticalReservation] = field(default_factory=list)
    horizontals: list[HorizontalReservation] = field(default_factory=list)
    state_quotas: list[StateQuotaConfig] = field(default_factory=list)
    tsp: list[TspConfig] = field(default_factory=list)
    supernumerary: list[SupernumeraryConfig] = field(default_factory=list)
    exs_priorities: list[ExsPriority] = field(default_factory=list)

    # --- derived look-ups (built by validate()) ---
    vertical_pct: dict[Vertical, float] = field(default_factory=dict)
    horizontal_pct: dict[Horizontal, float] = field(default_factory=dict)
    state_quota_pct: dict[StateQuota, float] = field(default_factory=dict)
    exs_priority_map: dict[ExsCode, int] = field(default_factory=dict)
    supernumerary_map: dict[SupernumeraryKind, SupernumeraryConfig] = field(
        default_factory=dict,
    )

    def validate(self) -> list[str]:
        """Check invariants and populate derived look-ups.  Returns warnings."""
        warnings: list[str] = []

        self.vertical_pct = {v.vertical: v.percent for v in self.verticals}
        total_v = sum(self.vertical_pct.values())
        if abs(total_v - 100.0) > 0.01:
            warnings.append(
                f"Vertical reservation percentages sum to {total_v}%, not 100%."
            )

        self.horizontal_pct = {h.axis: h.percent for h in self.horizontals}

        self.state_quota_pct = {sq.quota: sq.percent for sq in self.state_quotas}
        total_sq = sum(self.state_quota_pct.values())
        if abs(total_sq - 100.0) > 0.01:
            warnings.append(
                f"State quota percentages sum to {total_sq}%, not 100%."
            )

        self.exs_priority_map = {ep.code: ep.priority for ep in self.exs_priorities}
        self.supernumerary_map = {s.kind: s for s in self.supernumerary}

        return warnings


# ---------------------------------------------------------------------------
# REAP defaults
# ---------------------------------------------------------------------------

def reap_defaults() -> ReservationPolicy:
    """Return the REAP-2026 default reservation policy."""
    policy = ReservationPolicy(
        verticals=[
            VerticalReservation(vertical=Vertical.GEN, percent=36),
            VerticalReservation(vertical=Vertical.SC, percent=16),
            VerticalReservation(vertical=Vertical.ST, percent=12),
            VerticalReservation(vertical=Vertical.OBC, percent=21),
            VerticalReservation(vertical=Vertical.MBC, percent=5),
            VerticalReservation(vertical=Vertical.EWS, percent=10),
        ],
        horizontals=[
            HorizontalReservation(
                axis=Horizontal.WOMEN, percent=30,
                scope="within_each_vertical",
                conversion_if_unfilled="convert_to_male_same_vertical",
            ),
            HorizontalReservation(
                axis=Horizontal.PWD, percent=5,
                scope="within_each_vertical",
                conversion_if_unfilled="convert_to_non_pwd_same_vertical",
            ),
            HorizontalReservation(
                axis=Horizontal.EXS, percent=3,
                scope="within_each_vertical",
                conversion_if_unfilled="convert_to_non_exs_same_vertical",
                girls_sub_reservation=50,
            ),
        ],
        state_quotas=[
            StateQuotaConfig(
                quota=StateQuota.RSQ, percent=85,
                domicile="rajasthan", applies_to="all",
                conversion_if_unfilled="none",
            ),
            StateQuotaConfig(
                quota=StateQuota.ORS, percent=15,
                domicile="non_rajasthan",
                applies_to="private OR sfs_in_autonomous_govt OR govt_university",
                conversion_if_unfilled="merge_to_rsq_gen",
            ),
        ],
        tsp=[
            TspConfig(
                applies_to="is_tsp_area",
                parent_vertical=Vertical.ST,
                sub_quota_percent=45,
                conversion_if_unfilled="convert_to_parent_vertical",
            ),
        ],
        supernumerary=[
            SupernumeraryConfig(
                kind=SupernumeraryKind.TFWS, percent=5,
                eligibility="family_income<=800000 AND course_50pct_filled_last_year",
                convertible=False,
                notes="NOT for B.Arch; FINAL allotment; separate rank list",
            ),
            SupernumeraryConfig(
                kind=SupernumeraryKind.KM, percent=5,
                eligibility="is_kashmiri_migrant",
                convertible=False,
            ),
            SupernumeraryConfig(
                kind=SupernumeraryKind.FOREIGN_OCI, percent=15,
                eligibility="is_foreign OR is_oci",
                convertible=False,
                notes="1/3 reserved for Gulf children",
            ),
            SupernumeraryConfig(
                kind=SupernumeraryKind.WORKING_PROF, percent=0,
                eligibility="is_working_professional AND experience>=2 AND distance<=80km",
                convertible=False,
                notes="Opt-in per institute",
            ),
            SupernumeraryConfig(
                kind=SupernumeraryKind.PM_USPY, percent=0,
                convertible=False,
                notes="Off by default",
            ),
        ],
        exs_priorities=[
            ExsPriority(code=ExsCode.EXS1, priority=1, description="Widows/wards of killed in action"),
            ExsPriority(code=ExsCode.EXS2, priority=2, description="Wards of disabled in action and boarded out"),
            ExsPriority(code=ExsCode.EXS3, priority=3, description="Widows/wards died in service (attributable)"),
            ExsPriority(code=ExsCode.EXS4, priority=4, description="Wards disabled in service (attributable)"),
            ExsPriority(code=ExsCode.EXS5, priority=5, description="Wards with Gallantry Awards"),
            ExsPriority(code=ExsCode.EXS6, priority=6, description="Wards of Ex-Servicemen"),
            ExsPriority(code=ExsCode.EXS7, priority=7, description="Wives of disabled/gallantry defence"),
            ExsPriority(code=ExsCode.EXS8, priority=8, description="Wards of Serving Personnel"),
            ExsPriority(code=ExsCode.EXS9, priority=9, description="Wives of Serving Personnel"),
        ],
    )
    policy.validate()
    return policy


# ---------------------------------------------------------------------------
# Load from directory
# ---------------------------------------------------------------------------

def load_policy(data_dir: str | Path) -> ReservationPolicy:
    """Load all reservation config CSVs from *data_dir*."""
    d = Path(data_dir)

    policy = ReservationPolicy()

    p = d / "reservation_config.csv"
    if p.exists():
        policy.verticals = load_vertical_reservations(p)

    p = d / "horizontal_config.csv"
    if p.exists():
        policy.horizontals = load_horizontal_reservations(p)

    p = d / "state_quota_config.csv"
    if p.exists():
        policy.state_quotas = load_state_quota_configs(p)

    p = d / "tsp_config.csv"
    if p.exists():
        policy.tsp = load_tsp_config(p)

    p = d / "supernumerary.csv"
    if p.exists():
        policy.supernumerary = load_supernumerary_configs(p)

    p = d / "exs_priority.csv"
    if p.exists():
        policy.exs_priorities = load_exs_priorities(p)

    if not policy.verticals:
        defaults = reap_defaults()
        policy.verticals = defaults.verticals
        policy.horizontals = policy.horizontals or defaults.horizontals
        policy.state_quotas = policy.state_quotas or defaults.state_quotas
        policy.tsp = policy.tsp or defaults.tsp
        policy.supernumerary = policy.supernumerary or defaults.supernumerary
        policy.exs_priorities = policy.exs_priorities or defaults.exs_priorities

    policy.validate()
    return policy
