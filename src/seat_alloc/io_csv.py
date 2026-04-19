"""CSV and Excel I/O for all REAP seat-allocation data files.

Every public function returns plain Python objects (lists of pydantic models)
or DataFrames, and raises ``ValueError`` with a human-readable message on
invalid input.
"""

from __future__ import annotations

from pathlib import Path
from typing import TypeVar

import pandas as pd
from pydantic import BaseModel, ValidationError

from .models import (
    Allocation,
    Choice,
    ExsPriority,
    HorizontalReservation,
    Institute,
    Program,
    Rank,
    RoundConfig,
    SeatSlot,
    StateQuotaConfig,
    Student,
    SupernumeraryConfig,
    TspConfig,
    VerticalReservation,
)

T = TypeVar("T", bound=BaseModel)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TRUTHY = {"yes", "true", "1", "y"}
_FALSY = {"no", "false", "0", "n", ""}


def _to_bool(val: object) -> bool:
    if isinstance(val, bool):
        return val
    s = str(val).strip().lower()
    if s in _TRUTHY:
        return True
    if s in _FALSY:
        return False
    raise ValueError(f"Cannot interpret '{val}' as boolean")


def _read_df(path: str | Path) -> pd.DataFrame:
    """Read a CSV or Excel file into a DataFrame."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"File not found: {p}")
    if p.suffix in (".xlsx", ".xls"):
        df = pd.read_excel(p, engine="openpyxl")
    else:
        df = pd.read_csv(p)
    df.columns = [c.strip() for c in df.columns]
    return df


def _save_df(df: pd.DataFrame, path: str | Path) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    if p.suffix in (".xlsx", ".xls"):
        df.to_excel(p, index=False, engine="openpyxl")
    else:
        df.to_csv(p, index=False)


def _suggest_column(bad: str, valid: list[str]) -> str:
    """Return a 'did you mean …?' hint using edit distance."""
    from difflib import get_close_matches
    matches = get_close_matches(bad, valid, n=1, cutoff=0.5)
    if matches:
        return f" - did you mean '{matches[0]}'?"
    return ""


def _validate_columns(df: pd.DataFrame, required: list[str], source: str) -> None:
    """Raise if any required columns are missing from *df*."""
    missing = [c for c in required if c not in df.columns]
    if missing:
        hints = [f"'{c}'{_suggest_column(c, list(df.columns))}" for c in missing]
        raise ValueError(
            f"{source}: missing required column(s): {', '.join(hints)}. "
            f"Available columns: {list(df.columns)}"
        )


def _parse_rows(df: pd.DataFrame, model: type[T], source: str) -> list[T]:
    """Convert every row of *df* into a pydantic model, collecting errors."""
    items: list[T] = []
    errors: list[str] = []
    for idx, row in df.iterrows():
        row_dict = {k: (None if pd.isna(v) else v) for k, v in row.items()}
        for k, v in row_dict.items():
            if isinstance(v, str):
                row_dict[k] = v.strip()
        try:
            items.append(model.model_validate(row_dict))
        except ValidationError as exc:
            row_num = idx + 2  # 1-indexed + header row
            for e in exc.errors():
                field = ".".join(str(x) for x in e["loc"])
                errors.append(f"Row {row_num}, column '{field}': {e['msg']}")
    if errors:
        raise ValueError(f"{source} has validation errors:\n" + "\n".join(errors))
    return items


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------

def load_institutes(path: str | Path) -> list[Institute]:
    df = _read_df(path)
    _validate_columns(df, ["code", "name", "type"], str(path))
    if "is_tsp_area" in df.columns:
        df["is_tsp_area"] = df["is_tsp_area"].apply(_to_bool)
    else:
        df["is_tsp_area"] = False
    return _parse_rows(df, Institute, str(path))


def load_programs(path: str | Path) -> list[Program]:
    df = _read_df(path)
    _validate_columns(df, ["institute_code", "program_code", "name", "approved_intake"], str(path))
    for col in ("gas_seats", "sfs_seats", "management_quota_seats"):
        if col not in df.columns:
            df[col] = 0
    if "last_year_fill_pct" not in df.columns:
        df["last_year_fill_pct"] = 100.0
    if "programme" not in df.columns:
        df["programme"] = "BE_BTECH_BPLAN"
    return _parse_rows(df, Program, str(path))


def load_seat_matrix(path: str | Path) -> list[SeatSlot]:
    df = _read_df(path)
    _validate_columns(df, ["institute_code", "program_code", "capacity"], str(path))
    for col in ("seat_type", "state_quota", "vertical", "horizontal",
                "tsp_subquota", "supernumerary_kind"):
        if col not in df.columns:
            df[col] = None
    if "is_supernumerary" in df.columns:
        df["is_supernumerary"] = df["is_supernumerary"].apply(_to_bool)
    else:
        df["is_supernumerary"] = False
    return _parse_rows(df, SeatSlot, str(path))


def load_students(path: str | Path) -> list[Student]:
    df = _read_df(path)
    _validate_columns(df, ["application_no"], str(path))
    bool_cols = [
        "is_pwd", "is_tsp_area_resident", "is_kashmiri_migrant",
        "is_sports_category_a", "is_foreign", "is_oci", "is_gulf_child",
        "is_working_professional", "has_paid_fee",
    ]
    for col in bool_cols:
        if col in df.columns:
            df[col] = df[col].apply(_to_bool)
        else:
            df[col] = False
    for col in ("name", "domicile_state"):
        if col not in df.columns:
            df[col] = ""
    if "vertical_category" not in df.columns:
        df["vertical_category"] = "GEN"
    if "gender" not in df.columns:
        df["gender"] = "MALE"
    if "programme" not in df.columns:
        df["programme"] = "BE_BTECH_BPLAN"
    return _parse_rows(df, Student, str(path))


def load_ranks(path: str | Path) -> list[Rank]:
    df = _read_df(path)
    _validate_columns(df, ["application_no", "category", "rank"], str(path))
    return _parse_rows(df, Rank, str(path))


def load_choices(path: str | Path) -> list[Choice]:
    df = _read_df(path)
    _validate_columns(df, ["application_no", "preference_order", "institute_code", "program_code"], str(path))
    return _parse_rows(df, Choice, str(path))


def load_round_configs(path: str | Path) -> list[RoundConfig]:
    df = _read_df(path)
    _validate_columns(df, ["round_no", "name", "mode"], str(path))
    for col in ("eligible_filter", "rank_list", "merge_after", "notes"):
        if col not in df.columns:
            df[col] = ""
        else:
            df[col] = df[col].fillna("").astype(str)
    for col in ("requires_reported", "requires_paid"):
        if col in df.columns:
            df[col] = df[col].apply(_to_bool)
        else:
            df[col] = False
    return _parse_rows(df, RoundConfig, str(path))


def load_vertical_reservations(path: str | Path) -> list[VerticalReservation]:
    df = _read_df(path)
    _validate_columns(df, ["vertical", "percent"], str(path))
    return _parse_rows(df, VerticalReservation, str(path))


def load_horizontal_reservations(path: str | Path) -> list[HorizontalReservation]:
    df = _read_df(path)
    _validate_columns(df, ["axis", "percent"], str(path))
    for col in ("scope", "conversion_if_unfilled"):
        if col not in df.columns:
            df[col] = ""
    if "girls_sub_reservation" not in df.columns:
        df["girls_sub_reservation"] = 0.0
    return _parse_rows(df, HorizontalReservation, str(path))


def load_state_quota_configs(path: str | Path) -> list[StateQuotaConfig]:
    df = _read_df(path)
    _validate_columns(df, ["quota", "percent"], str(path))
    for col in ("domicile", "applies_to", "conversion_if_unfilled"):
        if col not in df.columns:
            df[col] = ""
    return _parse_rows(df, StateQuotaConfig, str(path))


def load_tsp_config(path: str | Path) -> list[TspConfig]:
    df = _read_df(path)
    return _parse_rows(df, TspConfig, str(path))


def load_supernumerary_configs(path: str | Path) -> list[SupernumeraryConfig]:
    df = _read_df(path)
    _validate_columns(df, ["kind", "percent"], str(path))
    if "convertible" in df.columns:
        df["convertible"] = df["convertible"].apply(_to_bool)
    else:
        df["convertible"] = False
    for col in ("base", "eligibility", "notes"):
        if col not in df.columns:
            df[col] = ""
    return _parse_rows(df, SupernumeraryConfig, str(path))


def load_exs_priorities(path: str | Path) -> list[ExsPriority]:
    df = _read_df(path)
    _validate_columns(df, ["code", "priority"], str(path))
    if "description" not in df.columns:
        df["description"] = ""
    return _parse_rows(df, ExsPriority, str(path))


# ---------------------------------------------------------------------------
# Savers
# ---------------------------------------------------------------------------

def _models_to_df(items: list[BaseModel]) -> pd.DataFrame:
    if not items:
        return pd.DataFrame()
    return pd.DataFrame([m.model_dump() for m in items])


def save_seat_matrix(slots: list[SeatSlot], path: str | Path) -> None:
    _save_df(_models_to_df(slots), path)


def save_allocations(allocs: list[Allocation], path: str | Path) -> None:
    _save_df(_models_to_df(allocs), path)


def save_students(students: list[Student], path: str | Path) -> None:
    _save_df(_models_to_df(students), path)


def save_df(df: pd.DataFrame, path: str | Path) -> None:
    """Generic save for any DataFrame (reports, cutoffs, etc.)."""
    _save_df(df, path)


# ---------------------------------------------------------------------------
# Index builders
# ---------------------------------------------------------------------------

def build_rank_index(ranks: list[Rank]) -> dict[str, dict[str, int]]:
    """Return {application_no: {category: rank}}."""
    idx: dict[str, dict[str, int]] = {}
    for r in ranks:
        idx.setdefault(r.application_no, {})[r.category] = r.rank
    return idx


def build_choice_index(choices: list[Choice]) -> dict[str, list[Choice]]:
    """Return {application_no: [choices sorted by preference_order]}."""
    idx: dict[str, list[Choice]] = {}
    for c in choices:
        idx.setdefault(c.application_no, []).append(c)
    for v in idx.values():
        v.sort(key=lambda c: c.preference_order)
    return idx
