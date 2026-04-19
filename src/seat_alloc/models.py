"""Pydantic models for the REAP-2026 Seat Allocation Simulator."""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class InstituteType(str, Enum):
    GOVT = "GOVT"
    GOVT_AIDED = "GOVT_AIDED"
    PRIVATE = "PRIVATE"
    UNIVERSITY = "UNIVERSITY"


class StateQuota(str, Enum):
    RSQ = "RSQ"
    ORS = "ORS"


class SeatType(str, Enum):
    GAS = "GAS"
    SFS = "SFS"


class Vertical(str, Enum):
    GEN = "GEN"
    SC = "SC"
    ST = "ST"
    OBC = "OBC"
    MBC = "MBC"
    EWS = "EWS"


class Horizontal(str, Enum):
    WOMEN = "WOMEN"
    PWD = "PWD"
    EXS = "EXS"
    EXS_GIRLS = "EXS_GIRLS"


class SupernumeraryKind(str, Enum):
    TFWS = "TFWS"
    KM = "KM"
    FOREIGN_OCI = "FOREIGN_OCI"
    WORKING_PROF = "WORKING_PROF"
    PM_USPY = "PM_USPY"


class ExsCode(str, Enum):
    EXS1 = "EXS1"
    EXS2 = "EXS2"
    EXS3 = "EXS3"
    EXS4 = "EXS4"
    EXS5 = "EXS5"
    EXS6 = "EXS6"
    EXS7 = "EXS7"
    EXS8 = "EXS8"
    EXS9 = "EXS9"


class Programme(str, Enum):
    BE_BTECH_BPLAN = "BE_BTECH_BPLAN"
    BARCH = "BARCH"


class Gender(str, Enum):
    MALE = "MALE"
    FEMALE = "FEMALE"
    OTHER = "OTHER"


class ReportingStatus(str, Enum):
    PENDING = "PENDING"
    REPORTED = "REPORTED"
    CONDITIONALLY_REPORTED = "CONDITIONALLY_REPORTED"
    SPECIAL_CONDITIONALLY_REPORTED = "SPECIAL_CONDITIONALLY_REPORTED"
    CANCELLED = "CANCELLED"


class Decision(str, Enum):
    FREEZE = "FREEZE"
    ALLOW_UPGRADE = "ALLOW_UPGRADE"
    WITHDRAW = "WITHDRAW"


class RoundMode(str, Enum):
    MOCK = "mock"
    FRESH = "fresh"
    UPWARD = "upward"
    SLIDING = "sliding"
    SPOT = "spot"


# ---------------------------------------------------------------------------
# Core data models
# ---------------------------------------------------------------------------

class Institute(BaseModel):
    code: str
    name: str
    type: InstituteType
    is_tsp_area: bool = False


class Program(BaseModel):
    institute_code: str
    program_code: str
    name: str
    programme: Programme = Programme.BE_BTECH_BPLAN
    approved_intake: int
    gas_seats: int = 0
    sfs_seats: int = 0
    last_year_fill_pct: float = 100.0
    management_quota_seats: int = 0


class SeatSlot(BaseModel):
    """Atomic unit the allocator fills."""
    institute_code: str
    program_code: str
    seat_type: SeatType | None = None
    state_quota: StateQuota | None = None
    vertical: Vertical | None = None
    horizontal: Horizontal | None = None
    tsp_subquota: Literal["TSP", "NON_TSP"] | None = None
    capacity: int
    is_supernumerary: bool = False
    supernumerary_kind: SupernumeraryKind | None = None

    @property
    def bucket_key(self) -> tuple:
        """Unique identity of this seat bucket."""
        return (
            self.institute_code,
            self.program_code,
            self.seat_type,
            self.state_quota,
            self.vertical,
            self.horizontal,
            self.tsp_subquota,
            self.is_supernumerary,
            self.supernumerary_kind,
        )

    def category_token(self) -> str:
        """Return the category string (e.g. 'SC-WOMEN') that maps to ranks.csv."""
        if self.supernumerary_kind:
            return self.supernumerary_kind.value
        parts: list[str] = []
        if self.vertical:
            parts.append(self.vertical.value)
        if self.tsp_subquota == "TSP":
            parts.append("TSP")
        if self.horizontal and self.horizontal != Horizontal.EXS_GIRLS:
            parts.append(self.horizontal.value)
        elif self.horizontal == Horizontal.EXS_GIRLS:
            parts.append("EXS")
        return "-".join(parts) if parts else "GEN"


class Student(BaseModel):
    """Student profile — ranks live in a separate Rank table."""
    application_no: str
    name: str = ""
    programme: Programme = Programme.BE_BTECH_BPLAN
    vertical_category: Vertical = Vertical.GEN
    gender: Gender = Gender.MALE
    is_pwd: bool = False
    exs_code: ExsCode | None = None
    domicile_state: str = ""
    is_tsp_area_resident: bool = False
    is_kashmiri_migrant: bool = False
    is_sports_category_a: bool = False
    family_income: float | None = None
    is_foreign: bool = False
    is_oci: bool = False
    is_gulf_child: bool = False
    is_working_professional: bool = False
    work_experience_years: float = 0.0
    workplace_distance_km: float = 0.0
    reporting_status: ReportingStatus | None = None
    has_paid_fee: bool = False
    decision: Decision | None = None

    @property
    def is_rajasthan_domicile(self) -> bool:
        return self.domicile_state.upper() in ("RAJASTHAN", "RJ")

    @property
    def is_female(self) -> bool:
        return self.gender == Gender.FEMALE

    @property
    def is_tfws_eligible(self) -> bool:
        return (
            self.family_income is not None
            and self.family_income <= 800_000
            and self.programme != Programme.BARCH
        )


class Rank(BaseModel):
    """One (student, category_combination) rank entry."""
    application_no: str
    category: str
    rank: int


class Choice(BaseModel):
    application_no: str
    preference_order: int
    institute_code: str
    program_code: str


class Allocation(BaseModel):
    """Result of a single-round allocation for one student."""
    round_no: int
    application_no: str
    institute_code: str
    program_code: str
    seat_type: SeatType | None = None
    state_quota: StateQuota | None = None
    vertical: Vertical | None = None
    horizontal: Horizontal | None = None
    tsp_subquota: str | None = None
    supernumerary_kind: SupernumeraryKind | None = None
    decision: Decision | None = None
    reporting_status: ReportingStatus | None = None

    @property
    def category_token(self) -> str:
        if self.supernumerary_kind:
            return self.supernumerary_kind.value
        parts: list[str] = []
        if self.vertical:
            parts.append(self.vertical.value)
        if self.horizontal:
            parts.append(self.horizontal.value)
        return "-".join(parts) if parts else "GEN"


# ---------------------------------------------------------------------------
# Config models
# ---------------------------------------------------------------------------

class RoundConfig(BaseModel):
    round_no: int
    name: str
    mode: RoundMode
    eligible_filter: str = "all"
    requires_reported: bool = False
    requires_paid: bool = False
    rank_list: str = "main"
    merge_after: str = ""
    notes: str = ""


class VerticalReservation(BaseModel):
    vertical: Vertical
    percent: float


class HorizontalReservation(BaseModel):
    axis: Horizontal
    percent: float
    scope: str = "within_each_vertical"
    conversion_if_unfilled: str = ""
    girls_sub_reservation: float = 0.0


class TspConfig(BaseModel):
    applies_to: str = "is_tsp_area"
    parent_vertical: Vertical = Vertical.ST
    sub_quota_percent: float = 45.0
    conversion_if_unfilled: str = "convert_to_parent_vertical"


class SupernumeraryConfig(BaseModel):
    kind: SupernumeraryKind
    percent: float
    base: str = "approved_intake"
    eligibility: str = ""
    convertible: bool = False
    notes: str = ""


class StateQuotaConfig(BaseModel):
    quota: StateQuota
    percent: float
    domicile: str = ""
    applies_to: str = "all"
    conversion_if_unfilled: str = "none"


class ExsPriority(BaseModel):
    code: ExsCode
    priority: int
    description: str = ""
