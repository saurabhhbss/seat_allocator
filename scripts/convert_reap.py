#!/usr/bin/env -S uv run python
"""Convert real REAP-2026 source files to the engine's CSV schema.

Usage:
    uv run python scripts/convert_reap.py \
        --sm    resources/SM_download1.xlsx \
        --merit resources/data1.xlsx \
        --opts  resources/option.DBF \
        --out   data/

Writes:
    data/seat_matrix.csv
    data/students.csv
    data/ranks.csv
    data/choices.csv
"""

from __future__ import annotations

import click
import pandas as pd
from dbfread import DBF
from pathlib import Path


# ---------------------------------------------------------------------------
# Seat matrix conversion
# ---------------------------------------------------------------------------

# Maps (SM column, vertical, horizontal, tsp_subquota) for RSQ rows.
# Only non-zero capacities will be emitted.
_RSQ_COLS: list[tuple[str, str, str, str]] = [
    ("General_Open",       "GEN", "",         ""),
    ("General_Female",     "GEN", "WOMEN",    ""),
    ("OBC_Open",           "OBC", "",         ""),
    ("OBC_Female",         "OBC", "WOMEN",    ""),
    ("MBC_Open",           "MBC", "",         ""),
    ("MBC_Female",         "MBC", "WOMEN",    ""),
    ("EWS_Open",           "EWS", "",         ""),
    ("EWS_Female",         "EWS", "WOMEN",    ""),
    ("SC_Open",            "SC",  "",         ""),
    ("SC_Female",          "SC",  "WOMEN",    ""),
    ("ST_Non_TSP_Open",    "ST",  "",         "NON_TSP"),
    ("ST_Non_TSP_Female",  "ST",  "WOMEN",    "NON_TSP"),
    ("TSP_Open",           "ST",  "",         "TSP"),
    ("TSP_Female",         "ST",  "WOMEN",    "TSP"),
    ("EXS_Open",           "GEN", "EXS",      ""),
    ("EXS_Female",         "GEN", "EXS_GIRLS",""),
    ("PWD_Open",           "GEN", "PWD",      ""),
    ("PWD_Female",         "GEN", "PWD",      ""),   # PWD women fold into PWD
]

_SUPERNUMERARY_COLS: list[tuple[str, str]] = [
    ("TFW_Seats", "TFWS"),
    ("KM_Seats",  "KM"),
    ("OCI_Seats", "FOREIGN_OCI"),
    ("WP_Seats",  "WORKING_PROF"),
]


def _to_int(val) -> int:
    try:
        return int(float(str(val)))
    except (ValueError, TypeError):
        return 0


def convert_seat_matrix(xlsx_path: str) -> pd.DataFrame:
    sm = pd.read_excel(xlsx_path, dtype=str)

    # Normalise column whitespace
    sm.columns = sm.columns.str.strip()
    for col in sm.select_dtypes(include="str").columns:
        sm[col] = sm[col].str.strip()

    # Filter: skip rows where allow is False or StopPayment is set
    sm = sm[sm["allow"].str.lower().isin(["true", "1", "yes"])].copy()
    sm = sm[sm["StopPayment"].isna() | (sm["StopPayment"] == "")].copy()
    sm = sm.reset_index(drop=True)

    rows: list[dict] = []

    for _, r in sm.iterrows():
        inst  = str(r["CollegeCode"])
        prog  = str(r["BranchCode"])
        stype = str(r["category"])      # SFS or GAS
        is_pvt   = str(r["govt_pvt"]).lower().startswith("private")
        is_govt  = not is_pvt
        is_sfs   = (stype == "SFS")

        # --- RSQ rows ---
        for col, vert, horiz, tsp in _RSQ_COLS:
            if col not in sm.columns:
                continue
            cap = _to_int(r.get(col, 0))
            if cap <= 0:
                continue
            rows.append({
                "institute_code":    inst,
                "program_code":      prog,
                "seat_type":         stype,
                "state_quota":       "RSQ",
                "vertical":          vert,
                "horizontal":        horiz,
                "tsp_subquota":      tsp,
                "capacity":          cap,
                "is_supernumerary":  "no",
                "supernumerary_kind": "",
            })

        # --- Supernumerary rows ---
        for col, kind in _SUPERNUMERARY_COLS:
            if col not in sm.columns:
                continue
            cap = _to_int(r.get(col, 0))
            if cap <= 0:
                continue
            rows.append({
                "institute_code":    inst,
                "program_code":      prog,
                "seat_type":         stype,
                "state_quota":       "RSQ",
                "vertical":          "",
                "horizontal":        "",
                "tsp_subquota":      "",
                "capacity":          cap,
                "is_supernumerary":  "yes",
                "supernumerary_kind": kind,
            })

        # --- ORS row (Section 4.D: private OR govt SFS only) ---
        if "Out_of_Raj_Quota_Total" in sm.columns:
            ors_cap = _to_int(r.get("Out_of_Raj_Quota_Total", 0))
            if ors_cap > 0 and (is_pvt or (is_govt and is_sfs)):
                rows.append({
                    "institute_code":    inst,
                    "program_code":      prog,
                    "seat_type":         stype,
                    "state_quota":       "ORS",
                    "vertical":          "GEN",
                    "horizontal":        "",
                    "tsp_subquota":      "",
                    "capacity":          ors_cap,
                    "is_supernumerary":  "no",
                    "supernumerary_kind": "",
                })

        # Management quota (private colleges, Round 10) is carved from General seats
        # and handled by special_round.py — no separate seat_matrix row needed.

    return pd.DataFrame(rows, columns=[
        "institute_code", "program_code", "seat_type", "state_quota",
        "vertical", "horizontal", "tsp_subquota", "capacity",
        "is_supernumerary", "supernumerary_kind",
    ])


# ---------------------------------------------------------------------------
# Students + ranks conversion
# ---------------------------------------------------------------------------

_RANK_COLS: list[tuple[str, str]] = [
    ("mgen",  "GEN"),
    ("mgenf", "GEN-WOMEN"),
    ("mews",  "EWS"),
    ("mewsf", "EWS-WOMEN"),
    ("mobc",  "OBC"),
    ("mobcf", "OBC-WOMEN"),
    ("mmbc",  "MBC"),
    ("mmbcf", "MBC-WOMEN"),
    ("msc",   "SC"),
    ("mscf",  "SC-WOMEN"),
    ("mst",   "ST"),
    ("mstf",  "ST-WOMEN"),
    ("mtsp",  "ST-TSP"),
    ("mtspf", "ST-TSP-WOMEN"),
    ("mkm",   "KM"),
    ("mkmf",  "KM-WOMEN"),
    ("mtfw",  "TFWS"),
    ("mexs",  "GEN-EXS"),
    ("mexsf", "GEN-EXS"),       # EXS_GIRLS token is also "GEN-EXS"
    ("mph",   "GEN-PWD"),
    ("mphf",  "GEN-PWD"),
    ("msqa",  "SQ"),
]


def _bool_val(series_val) -> str:
    if pd.isna(series_val) or str(series_val).strip() == "":
        return "no"
    return "yes" if str(series_val).strip().lower() not in ("", "0", "false", "no", "nan") else "no"


def convert_students_and_ranks(xlsx_path: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    df = pd.read_excel(xlsx_path, dtype=str)
    df.columns = df.columns.str.strip()
    for col in df.select_dtypes(include="str").columns:
        df[col] = df[col].str.strip()

    # Keep only non-rejected students
    df = df[df["rejected"].str.lower() != "true"].copy()
    df = df.reset_index(drop=True)

    students: list[dict] = []
    ranks: list[dict] = []

    for _, r in df.iterrows():
        app_no = str(r["formno"])

        # --- is_pwd: subcat='PH' or mph/mphf rank present ---
        has_ph_subcat = str(r.get("subcat", "")).upper() == "PH"
        has_pwd_rank = (
            _to_int(r.get("mph", 0)) > 0 or _to_int(r.get("mphf", 0)) > 0
        )
        is_pwd = "yes" if (has_ph_subcat or has_pwd_rank) else "no"

        # --- is_kashmiri_migrant: subcat='KM' or mkm rank present ---
        has_km_subcat = str(r.get("subcat", "")).upper() == "KM"
        has_km_rank = (
            _to_int(r.get("mkm", 0)) > 0 or _to_int(r.get("mkmf", 0)) > 0
        )
        is_km = "yes" if (has_km_subcat or has_km_rank) else "no"

        # --- is_tsp_area_resident: mtsp or mtspf rank present ---
        has_tsp_rank = (
            _to_int(r.get("mtsp", 0)) > 0 or _to_int(r.get("mtspf", 0)) > 0
        )
        is_tsp = "yes" if has_tsp_rank else "no"

        # --- is_sports_category_a: Category A only (sq_cat == 'A' per REAP booklet) ---
        sq_cat = str(r.get("sq_cat", "")).strip().upper()
        is_sq = "yes" if sq_cat == "A" else "no"

        # --- family_income ---
        income_str = str(r.get("income", "")).lower()
        if income_str == "less8lacs":
            family_income = "800000"
        elif income_str == "above8lacs":
            family_income = "900000"
        else:
            family_income = ""

        # --- gender ---
        gender_raw = str(r.get("gender", "M")).upper().strip()
        gender = "FEMALE" if gender_raw == "F" else "MALE"

        # --- vertical_category: OBC→OBC (engine uses OBC not OBC-NCL) ---
        cat = str(r.get("category", "GEN")).upper().strip()

        # --- exs_code: already in EXS1-EXS9 format ---
        exs_val = str(r.get("excat", "")).strip()
        exs_code = exs_val if exs_val.upper().startswith("EXS") else ""

        students.append({
            "application_no":          app_no,
            "name":                    str(r.get("name", "")),
            "programme":               "BE_BTECH_BPLAN",
            "vertical_category":       cat,
            "gender":                  gender,
            "is_pwd":                  is_pwd,
            "exs_code":                exs_code,
            "domicile_state":          str(r.get("domicile", "")).upper(),
            "is_tsp_area_resident":    is_tsp,
            "is_kashmiri_migrant":     is_km,
            "is_sports_category_a":    is_sq,
            "family_income":           family_income,
            "is_foreign":              "no",
            "is_oci":                  "no",
            "is_gulf_child":           "no",
            "is_working_professional": "no",
        })

        # --- Ranks ---
        for col, category_token in _RANK_COLS:
            if col not in df.columns:
                continue
            val = r.get(col, "")
            rank = _to_int(val)
            if rank > 0:
                ranks.append({
                    "application_no": app_no,
                    "category":       category_token,
                    "rank":           rank,
                })

    students_df = pd.DataFrame(students, columns=[
        "application_no", "name", "programme", "vertical_category", "gender",
        "is_pwd", "exs_code", "domicile_state", "is_tsp_area_resident",
        "is_kashmiri_migrant", "is_sports_category_a", "family_income",
        "is_foreign", "is_oci", "is_gulf_child", "is_working_professional",
    ])
    ranks_df = pd.DataFrame(ranks, columns=["application_no", "category", "rank"])
    return students_df, ranks_df


# ---------------------------------------------------------------------------
# Choices conversion
# ---------------------------------------------------------------------------

def convert_choices(dbf_path: str, valid_formnos: set[str]) -> pd.DataFrame:
    table = DBF(dbf_path, load=True, encoding="latin-1")
    rows: list[dict] = []
    for rec in table:
        formno = str(rec["FORMNO"]).strip()
        if formno not in valid_formnos:
            continue
        rows.append({
            "application_no":   formno,
            "preference_order": int(rec["CHOICENUMB"]),
            "institute_code":   str(rec["COLLEGEID"]).strip(),
            "program_code":     str(rec["BRANCHCODE"]).strip(),
        })

    df = pd.DataFrame(rows, columns=[
        "application_no", "preference_order", "institute_code", "program_code",
    ])
    # Drop rows where institute or program code is missing (malformed DBF records)
    df = df.dropna(subset=["institute_code", "program_code"])
    df = df[df["institute_code"].str.strip() != ""]
    return df


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

@click.command()
@click.option("--sm",    required=True, help="Path to SM_download1.xlsx")
@click.option("--merit", required=True, help="Path to data1.xlsx")
@click.option("--opts",  required=True, help="Path to option.DBF")
@click.option("--out",   default="data", show_default=True, help="Output directory")
def main(sm: str, merit: str, opts: str, out: str) -> None:
    """Convert REAP source files to engine CSV format."""
    out_dir = Path(out)
    out_dir.mkdir(parents=True, exist_ok=True)

    click.echo("Converting seat matrix...")
    sm_df = convert_seat_matrix(sm)
    sm_df.to_csv(out_dir / "seat_matrix.csv", index=False)
    click.echo(f"  → {len(sm_df)} seat_matrix rows")

    click.echo("Converting students and ranks...")
    students_df, ranks_df = convert_students_and_ranks(merit)
    students_df.to_csv(out_dir / "students.csv", index=False)
    ranks_df.to_csv(out_dir / "ranks.csv", index=False)
    sq_count = (students_df["is_sports_category_a"] == "yes").sum()
    click.echo(f"  → {len(students_df)} students  ({sq_count} SQ)  |  {len(ranks_df)} rank entries")

    click.echo("Converting choices (this may take a moment for large DBF)...")
    valid_formnos = set(students_df["application_no"].astype(str))
    choices_df = convert_choices(opts, valid_formnos)
    choices_df.to_csv(out_dir / "choices.csv", index=False)
    click.echo(f"  → {len(choices_df)} choice entries")

    click.echo(f"\nDone. Files written to {out_dir}/")


if __name__ == "__main__":
    main()
