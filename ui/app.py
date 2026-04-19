"""Streamlit UI for the REAP-2026 Seat Allocation Simulator.

Wizard-style flow:
1. Load Data
2. Edit Data
3. Reservation Policy
4. Run Allocation
5. Results & Round Controls
"""

from __future__ import annotations

import io
from pathlib import Path

import pandas as pd
import streamlit as st

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="REAP-2026 Seat Allocator",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="expanded",
)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

# ---------------------------------------------------------------------------
# Lazy imports (keeps startup fast if streamlit caches)
# ---------------------------------------------------------------------------


@st.cache_resource
def _get_modules():
    from seat_alloc import io_csv, reservation_config, category_priority as cp_mod
    from seat_alloc.models import RoundConfig, RoundMode
    from seat_alloc.rounds import SimulationState, run_simulation
    from seat_alloc.reports import (
        allocation_table,
        per_round_summary,
        cutoff_table,
        vacancy_table,
        student_trace,
    )
    from seat_alloc.seat_expansion import expand
    return {
        "io": io_csv,
        "rc": reservation_config,
        "cp": cp_mod,
        "RoundConfig": RoundConfig,
        "RoundMode": RoundMode,
        "SimState": SimulationState,
        "run_sim": run_simulation,
        "alloc_tbl": allocation_table,
        "round_summary": per_round_summary,
        "cutoff_tbl": cutoff_table,
        "vacancy_tbl": vacancy_table,
        "student_trace": student_trace,
        "expand": expand,
    }


def _to_excel_bytes(df: pd.DataFrame) -> bytes:
    buf = io.BytesIO()
    df.to_excel(buf, index=False, engine="openpyxl")
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

STEPS = ["Load Data", "Edit Data", "Reservation Policy", "Run Allocation", "Results"]

if "step" not in st.session_state:
    st.session_state.step = 0

with st.sidebar:
    st.title("REAP-2026 Seat Allocator")
    st.divider()
    for i, name in enumerate(STEPS):
        icon = "●" if i == st.session_state.step else "○"
        if st.button(f"{icon} {i + 1}. {name}", key=f"nav_{i}", use_container_width=True):
            st.session_state.step = i
            st.rerun()
    st.divider()
    use_sample = st.toggle("Use sample data", value=True, help="Load bundled sample CSVs from data/")

# ---------------------------------------------------------------------------
# Step 1: Load Data
# ---------------------------------------------------------------------------


def _step_load():
    mods = _get_modules()
    io = mods["io"]
    st.header("Step 1: Load Data")
    st.write("Upload your CSV files or use the bundled sample data.")

    tabs = st.tabs(["Seat Matrix", "Students", "Ranks", "Choices"])

    loaded: dict[str, pd.DataFrame] = {}

    with tabs[0]:
        f = st.file_uploader("seat_matrix.csv", type=["csv", "xlsx"], key="ul_sm")
        if f:
            loaded["seat_matrix"] = pd.read_csv(f) if f.name.endswith(".csv") else pd.read_excel(f)
        elif use_sample and (DATA_DIR / "seat_matrix.csv").exists():
            loaded["seat_matrix"] = pd.read_csv(DATA_DIR / "seat_matrix.csv")
            st.success("Loaded sample seat_matrix.csv")
        if "seat_matrix" in loaded:
            st.dataframe(loaded["seat_matrix"], use_container_width=True, height=200)

    with tabs[1]:
        f = st.file_uploader("students.csv", type=["csv", "xlsx"], key="ul_st")
        if f:
            loaded["students"] = pd.read_csv(f) if f.name.endswith(".csv") else pd.read_excel(f)
        elif use_sample and (DATA_DIR / "students.csv").exists():
            loaded["students"] = pd.read_csv(DATA_DIR / "students.csv")
            st.success("Loaded sample students.csv")
        if "students" in loaded:
            st.dataframe(loaded["students"], use_container_width=True, height=200)

    with tabs[2]:
        f = st.file_uploader("ranks.csv", type=["csv", "xlsx"], key="ul_rk")
        if f:
            loaded["ranks"] = pd.read_csv(f) if f.name.endswith(".csv") else pd.read_excel(f)
        elif use_sample and (DATA_DIR / "ranks.csv").exists():
            loaded["ranks"] = pd.read_csv(DATA_DIR / "ranks.csv")
            st.success("Loaded sample ranks.csv")
        if "ranks" in loaded:
            st.dataframe(loaded["ranks"], use_container_width=True, height=200)

    with tabs[3]:
        f = st.file_uploader("choices.csv", type=["csv", "xlsx"], key="ul_ch")
        if f:
            loaded["choices"] = pd.read_csv(f) if f.name.endswith(".csv") else pd.read_excel(f)
        elif use_sample and (DATA_DIR / "choices.csv").exists():
            loaded["choices"] = pd.read_csv(DATA_DIR / "choices.csv")
            st.success("Loaded sample choices.csv")
        if "choices" in loaded:
            st.dataframe(loaded["choices"], use_container_width=True, height=200)

    if loaded:
        st.session_state["loaded_data"] = loaded

    has_all = all(k in loaded for k in ("seat_matrix", "students", "ranks", "choices"))
    if has_all:
        st.success("All required files loaded.")
        if st.button("Next: Edit Data →", type="primary"):
            st.session_state.step = 1
            st.rerun()
    else:
        missing = [k for k in ("seat_matrix", "students", "ranks", "choices") if k not in loaded]
        st.warning(f"Missing: {', '.join(missing)}")


# ---------------------------------------------------------------------------
# Step 2: Edit Data
# ---------------------------------------------------------------------------


def _step_edit():
    st.header("Step 2: Edit Data")
    loaded = st.session_state.get("loaded_data", {})
    if not loaded:
        st.warning("No data loaded. Go to Step 1 first.")
        return

    tab_names = [k for k in ("seat_matrix", "students", "ranks", "choices") if k in loaded]
    tabs = st.tabs(tab_names)

    for tab, name in zip(tabs, tab_names):
        with tab:
            df = loaded[name]
            edited = st.data_editor(
                df, num_rows="dynamic", use_container_width=True, key=f"edit_{name}",
            )
            loaded[name] = edited
            col1, col2 = st.columns(2)
            with col1:
                csv_data = edited.to_csv(index=False).encode()
                st.download_button(f"Download {name}.csv", csv_data, f"{name}.csv", "text/csv")
            with col2:
                st.download_button(
                    f"Download {name}.xlsx",
                    _to_excel_bytes(edited),
                    f"{name}.xlsx",
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )

    st.session_state["loaded_data"] = loaded
    if st.button("Next: Reservation Policy →", type="primary"):
        st.session_state.step = 2
        st.rerun()


# ---------------------------------------------------------------------------
# Step 3: Reservation Policy
# ---------------------------------------------------------------------------


def _step_policy():
    mods = _get_modules()
    cp_mod = mods["cp"]
    rc_mod = mods["rc"]

    st.header("Step 3: Reservation Policy")

    tab_cp, tab_res, tab_hor = st.tabs(["Category Priority", "Vertical Reservation", "Horizontal Reservation"])

    with tab_cp:
        st.subheader("Category Priority Order")
        st.caption(
            "For each vertical category, define the order in which seat buckets "
            "are tried when allocating a choice. GEN first = merit-first rule."
        )
        if "category_priority" not in st.session_state:
            if (DATA_DIR / "category_priority.csv").exists():
                cp = cp_mod.load(DATA_DIR / "category_priority.csv")
            else:
                cp = cp_mod.reap_default()
            st.session_state["category_priority"] = cp.as_dataframe()

        cp_df = st.data_editor(
            st.session_state["category_priority"],
            use_container_width=True,
            key="edit_cp",
        )
        st.session_state["category_priority"] = cp_df

        col1, col2 = st.columns(2)
        with col1:
            if st.button("Reset to REAP defaults", key="reset_cp"):
                st.session_state["category_priority"] = cp_mod.reap_default().as_dataframe()
                st.rerun()
        with col2:
            st.download_button(
                "Download category_priority.csv",
                cp_df.to_csv(index=False).encode(),
                "category_priority.csv",
                "text/csv",
            )

    with tab_res:
        st.subheader("Vertical Reservations (within RSQ)")
        policy = rc_mod.reap_defaults()
        vert_df = pd.DataFrame([
            {"vertical": v.vertical.value, "percent": v.percent}
            for v in policy.verticals
        ])
        if "vert_res" not in st.session_state:
            st.session_state["vert_res"] = vert_df
        edited_vr = st.data_editor(st.session_state["vert_res"], key="edit_vr", use_container_width=True)
        st.session_state["vert_res"] = edited_vr
        total = edited_vr["percent"].sum()
        if abs(total - 100) > 0.01:
            st.warning(f"Percentages sum to {total}% (should be 100%)")
        else:
            st.success(f"Total: {total}%")

    with tab_hor:
        st.subheader("Horizontal Reservations")
        hor_df = pd.DataFrame([
            {"axis": h.axis.value, "percent": h.percent, "girls_sub_reservation": h.girls_sub_reservation}
            for h in policy.horizontals
        ])
        if "hor_res" not in st.session_state:
            st.session_state["hor_res"] = hor_df
        edited_hr = st.data_editor(st.session_state["hor_res"], key="edit_hr", use_container_width=True)
        st.session_state["hor_res"] = edited_hr

    if st.button("Next: Run Allocation →", type="primary"):
        st.session_state.step = 3
        st.rerun()


# ---------------------------------------------------------------------------
# Step 4: Run Allocation
# ---------------------------------------------------------------------------


def _step_run():
    mods = _get_modules()
    io = mods["io"]
    cp_mod = mods["cp"]
    rc_mod = mods["rc"]

    st.header("Step 4: Run Allocation")

    loaded = st.session_state.get("loaded_data", {})
    if not all(k in loaded for k in ("seat_matrix", "students", "ranks", "choices")):
        st.error("Data not loaded. Go back to Step 1.")
        return

    col1, col2 = st.columns(2)
    with col1:
        programme = st.selectbox("Programme", ["B.E./B.Tech/B.Plan", "B.Arch"])

    round_configs = _default_round_configs(mods, programme)
    st.write(f"**{len(round_configs)} rounds** configured for {programme}")
    st.dataframe(
        pd.DataFrame([rc.model_dump() for rc in round_configs]),
        use_container_width=True,
        height=200,
    )

    if st.button("Run Full Simulation", type="primary"):
        with st.spinner("Running allocation..."):
            try:
                seat_slots = io.load_seat_matrix(io.BytesIO if False else _df_to_tempcsv(loaded["seat_matrix"]))
                students = io.load_students(_df_to_tempcsv(loaded["students"]))
                ranks = io.load_ranks(_df_to_tempcsv(loaded["ranks"]))
                choices = io.load_choices(_df_to_tempcsv(loaded["choices"]))

                rank_idx = io.build_rank_index(ranks)
                choice_idx = io.build_choice_index(choices)

                cp_df = st.session_state.get("category_priority")
                if cp_df is not None:
                    tmp = _df_to_tempcsv(cp_df)
                    priority = cp_mod.load(tmp)
                else:
                    priority = cp_mod.reap_default()

                state = mods["run_sim"](
                    students, choice_idx, rank_idx, seat_slots,
                    priority, round_configs,
                )
                st.session_state["sim_state"] = state
                st.success(f"Simulation complete — {sum(len(r.allocations) for r in state.round_results)} total allocations across {len(state.round_results)} rounds.")
                st.session_state.step = 4
                st.rerun()

            except Exception as exc:
                st.error(f"Error: {exc}")
                import traceback
                st.code(traceback.format_exc())


def _df_to_tempcsv(df: pd.DataFrame) -> Path:
    """Write a DataFrame to a temp CSV and return the path."""
    import tempfile
    tmp = Path(tempfile.mktemp(suffix=".csv"))
    df.to_csv(tmp, index=False)
    return tmp


def _default_round_configs(mods, programme: str) -> list:
    RoundConfig = mods["RoundConfig"]
    RoundMode = mods["RoundMode"]

    if programme == "B.Arch":
        configs_path = DATA_DIR / "rounds_config_barch.csv"
    else:
        configs_path = DATA_DIR / "rounds_config_betech.csv"

    if configs_path.exists():
        return mods["io"].load_round_configs(configs_path)

    if programme == "B.Arch":
        return [
            RoundConfig(round_no=1, name="TFWS Counseling", mode=RoundMode.FRESH, eligible_filter="is_tfws_eligible", rank_list="tfws"),
            RoundConfig(round_no=2, name="TFWS Upward I", mode=RoundMode.UPWARD, eligible_filter="all", requires_reported=True, rank_list="tfws"),
            RoundConfig(round_no=3, name="Special Categories", mode=RoundMode.FRESH, eligible_filter="is_km OR is_pwd OR exs_code IS NOT NULL OR is_ors", merge_after="WOMEN"),
            RoundConfig(round_no=4, name="Special Upward", mode=RoundMode.UPWARD, eligible_filter="all", requires_reported=True, merge_after="PWD,EXS"),
            RoundConfig(round_no=5, name="Rajasthan Main", mode=RoundMode.FRESH, eligible_filter="is_rajasthan_domicile"),
            RoundConfig(round_no=6, name="RS Upward I", mode=RoundMode.UPWARD, eligible_filter="all", requires_reported=True),
            RoundConfig(round_no=7, name="RS Upward II", mode=RoundMode.UPWARD, eligible_filter="all", requires_reported=True),
            RoundConfig(round_no=8, name="Direct + Management", mode=RoundMode.SPOT),
        ]
    else:
        return [
            RoundConfig(round_no=0, name="Mock Round", mode=RoundMode.MOCK),
            RoundConfig(round_no=1, name="TFWS Counseling", mode=RoundMode.FRESH, eligible_filter="is_tfws_eligible", rank_list="tfws"),
            RoundConfig(round_no=2, name="TFWS Upward I", mode=RoundMode.UPWARD, eligible_filter="all", requires_reported=True, rank_list="tfws"),
            RoundConfig(round_no=3, name="TFWS Upward II", mode=RoundMode.UPWARD, eligible_filter="all", requires_reported=True, rank_list="tfws"),
            RoundConfig(round_no=4, name="Special Categories", mode=RoundMode.FRESH, eligible_filter="is_km OR is_pwd OR exs_code IS NOT NULL OR is_ors", merge_after="WOMEN"),
            RoundConfig(round_no=5, name="Special Upward", mode=RoundMode.UPWARD, eligible_filter="all", requires_reported=True, merge_after="PWD,EXS"),
            RoundConfig(round_no=6, name="Rajasthan Main", mode=RoundMode.FRESH, eligible_filter="is_rajasthan_domicile"),
            RoundConfig(round_no=7, name="RS Upward I", mode=RoundMode.UPWARD, eligible_filter="all", requires_reported=True),
            RoundConfig(round_no=8, name="RS Upward II", mode=RoundMode.UPWARD, eligible_filter="all", requires_reported=True),
            RoundConfig(round_no=9, name="Internal Sliding", mode=RoundMode.SLIDING),
            RoundConfig(round_no=10, name="Direct + Management", mode=RoundMode.SPOT),
        ]


# ---------------------------------------------------------------------------
# Step 5: Results
# ---------------------------------------------------------------------------


def _step_results():
    mods = _get_modules()
    st.header("Step 5: Results")

    state = st.session_state.get("sim_state")
    if state is None:
        st.warning("No simulation results. Run the allocation in Step 4 first.")
        return

    tab_summary, tab_allocs, tab_cutoffs, tab_vacancy, tab_trace = st.tabs(
        ["Summary", "Allocations", "Cutoffs", "Vacancies", "Student Trace"]
    )

    with tab_summary:
        st.subheader("Round Summary")
        df_summary = mods["round_summary"](state)
        st.dataframe(df_summary, use_container_width=True)
        st.download_button(
            "Download summary.xlsx",
            _to_excel_bytes(df_summary),
            "round_summary.xlsx",
        )

    with tab_allocs:
        st.subheader("All Allocations")
        all_allocs = []
        for rr in state.round_results:
            all_allocs.extend(rr.allocations)
        df_alloc = mods["alloc_tbl"](all_allocs)
        if not df_alloc.empty:
            st.dataframe(df_alloc, use_container_width=True, height=400)
            st.download_button(
                "Download allocations.xlsx",
                _to_excel_bytes(df_alloc),
                "allocations.xlsx",
            )

            st.subheader("Final Allocations")
            final_allocs = list(state.current_allocations.values())
            df_final = mods["alloc_tbl"](final_allocs)
            st.dataframe(df_final, use_container_width=True, height=400)
            st.download_button(
                "Download final_allocations.xlsx",
                _to_excel_bytes(df_final),
                "final_allocations.xlsx",
            )
        else:
            st.info("No allocations produced.")

    with tab_cutoffs:
        st.subheader("Opening & Closing Ranks")
        df_cut = mods["cutoff_tbl"](state)
        if not df_cut.empty:
            st.dataframe(df_cut, use_container_width=True, height=400)
            st.download_button("Download cutoffs.xlsx", _to_excel_bytes(df_cut), "cutoffs.xlsx")
        else:
            st.info("No cutoff data.")

    with tab_vacancy:
        st.subheader("Vacancy Report")
        df_vac = mods["vacancy_tbl"](state.seat_slots, state.current_allocations)
        if not df_vac.empty:
            st.dataframe(df_vac, use_container_width=True, height=400)
            total_cap = df_vac["capacity"].sum()
            total_filled = df_vac["filled"].sum()
            st.metric("Fill Rate", f"{total_filled}/{total_cap} ({100 * total_filled / max(total_cap, 1):.1f}%)")
            st.download_button("Download vacancies.xlsx", _to_excel_bytes(df_vac), "vacancies.xlsx")

    with tab_trace:
        st.subheader("Student Trace")
        app_no = st.text_input("Application number", placeholder="e.g. S001")
        if app_no:
            df_trace = mods["student_trace"](app_no, state)
            if df_trace.empty:
                st.info(f"No records found for '{app_no}'.")
            else:
                st.dataframe(df_trace, use_container_width=True)


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

step = st.session_state.step
if step == 0:
    _step_load()
elif step == 1:
    _step_edit()
elif step == 2:
    _step_policy()
elif step == 3:
    _step_run()
elif step == 4:
    _step_results()
