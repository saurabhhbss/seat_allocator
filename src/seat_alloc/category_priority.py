"""Load, validate, and generate the configurable category-priority CSV.

The ``category_priority.csv`` defines, for each vertical category, the
ordered list of seat-bucket categories a student should be tried against
when allocating a choice.  The engine filters this list at runtime to
only categories the student actually holds a rank for.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from .io_csv import _read_df, _save_df

VALID_VERTICALS = {"GEN", "SC", "ST", "OBC", "MBC", "EWS"}

VALID_CATEGORY_TOKENS = {
    "GEN", "GEN-WOMEN", "GEN-PWD", "GEN-EXS",
    "SC", "SC-WOMEN", "SC-PWD", "SC-EXS",
    "ST", "ST-WOMEN", "ST-PWD", "ST-EXS",
    "ST-TSP", "ST-TSP-WOMEN", "ST-TSP-PWD", "ST-TSP-EXS",
    "OBC", "OBC-WOMEN", "OBC-PWD", "OBC-EXS",
    "MBC", "MBC-WOMEN", "MBC-PWD", "MBC-EXS",
    "EWS", "EWS-WOMEN", "EWS-PWD", "EWS-EXS",
    "TFWS", "KM", "FOREIGN_OCI", "WORKING_PROF", "PM_USPY",
}


class CategoryPriority:
    """Maps each vertical to an ordered list of category tokens."""

    def __init__(self, mapping: dict[str, list[str]]) -> None:
        self._mapping = mapping

    def get_priority(self, vertical: str) -> list[str]:
        return list(self._mapping.get(vertical, []))

    @property
    def verticals(self) -> list[str]:
        return list(self._mapping.keys())

    def as_dataframe(self) -> pd.DataFrame:
        rows = []
        for vert, cats in self._mapping.items():
            rows.append({"vertical": vert, "priority_order": ",".join(cats)})
        return pd.DataFrame(rows)


def validate_priority(mapping: dict[str, list[str]]) -> list[str]:
    """Return a list of plain-English warnings/errors."""
    errors: list[str] = []
    for vert, cats in mapping.items():
        if vert not in VALID_VERTICALS:
            errors.append(f"Unknown vertical '{vert}'. Valid: {sorted(VALID_VERTICALS)}")
        for i, cat in enumerate(cats):
            if cat not in VALID_CATEGORY_TOKENS:
                errors.append(
                    f"Row '{vert}', position {i + 1}: unknown category token "
                    f"'{cat}'. Valid tokens: {sorted(VALID_CATEGORY_TOKENS)}"
                )
    missing = VALID_VERTICALS - set(mapping.keys())
    if missing:
        errors.append(f"Missing rows for verticals: {sorted(missing)}")
    return errors


def load(path: str | Path) -> CategoryPriority:
    """Load ``category_priority.csv``."""
    df = _read_df(path)
    if "vertical" not in df.columns or "priority_order" not in df.columns:
        raise ValueError(
            f"{path}: must have columns 'vertical' and 'priority_order'."
        )
    mapping: dict[str, list[str]] = {}
    for _, row in df.iterrows():
        vert = str(row["vertical"]).strip()
        raw = str(row["priority_order"]).strip()
        cats = [c.strip() for c in raw.split(",") if c.strip()]
        mapping[vert] = cats
    errors = validate_priority(mapping)
    if errors:
        raise ValueError(
            f"{path} has validation errors:\n" + "\n".join(errors)
        )
    return CategoryPriority(mapping)


def save(cp: CategoryPriority, path: str | Path) -> None:
    _save_df(cp.as_dataframe(), path)


def reap_default() -> CategoryPriority:
    """REAP-2026 default: GEN first, then own vertical; each with horizontals."""
    mapping: dict[str, list[str]] = {}
    for vert in ("GEN", "SC", "ST", "OBC", "MBC", "EWS"):
        cats = ["GEN", "GEN-WOMEN", "GEN-PWD", "GEN-EXS"]
        if vert != "GEN":
            cats += [vert, f"{vert}-WOMEN", f"{vert}-PWD", f"{vert}-EXS"]
        mapping[vert] = cats
    return CategoryPriority(mapping)
