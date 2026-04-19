"""CLI entry point — primarily a launcher for the Streamlit UI."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import click


@click.group(invoke_without_command=True)
@click.pass_context
def main(ctx: click.Context) -> None:
    """REAP-2026 Seat Allocation Simulator."""
    if ctx.invoked_subcommand is None:
        ctx.invoke(ui)


@main.command()
def ui() -> None:
    """Launch the Streamlit web UI (default)."""
    app_path = Path(__file__).resolve().parent.parent.parent / "ui" / "app.py"
    if not app_path.exists():
        click.echo(f"Error: UI file not found at {app_path}", err=True)
        sys.exit(1)
    click.echo(f"Starting REAP Seat Allocator UI …")
    subprocess.run(
        [sys.executable, "-m", "streamlit", "run", str(app_path),
         "--server.headless=false"],
        check=False,
    )


@main.command()
@click.option("--data", default="data", help="Path to data directory with CSVs")
@click.option("--out", default="out", help="Output directory for results")
def run(data: str, out: str) -> None:
    """Run the allocation headlessly and write results to CSVs."""
    from . import io_csv
    from .category_priority import load as load_cp, reap_default
    from .rounds import run_simulation
    from .reports import allocation_table, per_round_summary, cutoff_table, vacancy_table

    data_dir = Path(data)
    out_dir = Path(out)
    out_dir.mkdir(parents=True, exist_ok=True)

    click.echo(f"Loading data from {data_dir} …")
    seat_slots = io_csv.load_seat_matrix(data_dir / "seat_matrix.csv")
    students = io_csv.load_students(data_dir / "students.csv")
    ranks = io_csv.load_ranks(data_dir / "ranks.csv")
    choices = io_csv.load_choices(data_dir / "choices.csv")

    rank_idx = io_csv.build_rank_index(ranks)
    choice_idx = io_csv.build_choice_index(choices)

    cp_path = data_dir / "category_priority.csv"
    priority = load_cp(cp_path) if cp_path.exists() else reap_default()

    rc_path = data_dir / "rounds_config_betech.csv"
    if rc_path.exists():
        round_cfgs = io_csv.load_round_configs(rc_path)
    else:
        from .models import RoundConfig, RoundMode
        round_cfgs = [
            RoundConfig(round_no=0, name="Mock", mode=RoundMode.MOCK),
            RoundConfig(round_no=1, name="TFWS", mode=RoundMode.FRESH, eligible_filter="is_tfws_eligible", rank_list="tfws"),
            RoundConfig(round_no=2, name="Special", mode=RoundMode.FRESH, eligible_filter="is_km OR is_pwd OR exs_code IS NOT NULL OR is_ors", merge_after="WOMEN"),
            RoundConfig(round_no=3, name="Special Upward", mode=RoundMode.UPWARD, requires_reported=True, merge_after="PWD,EXS"),
            RoundConfig(round_no=4, name="Rajasthan Main", mode=RoundMode.FRESH, eligible_filter="is_rajasthan_domicile"),
            RoundConfig(round_no=5, name="RS Upward", mode=RoundMode.UPWARD, requires_reported=True),
        ]

    click.echo(f"Running {len(round_cfgs)} rounds …")
    state = run_simulation(students, choice_idx, rank_idx, seat_slots, priority, round_cfgs)

    summary = per_round_summary(state)
    io_csv.save_df(summary, out_dir / "round_summary.csv")

    all_allocs = []
    for rr in state.round_results:
        all_allocs.extend(rr.allocations)
    io_csv.save_df(allocation_table(all_allocs), out_dir / "allocations.csv")

    final = list(state.current_allocations.values())
    io_csv.save_df(allocation_table(final), out_dir / "final_allocations.csv")

    io_csv.save_df(cutoff_table(state), out_dir / "cutoffs.csv")
    io_csv.save_df(vacancy_table(state.seat_slots, state.current_allocations), out_dir / "vacancies.csv")

    click.echo(f"Done. Results written to {out_dir}/")
    total = sum(len(rr.allocations) for rr in state.round_results)
    click.echo(f"  {total} allocations across {len(state.round_results)} rounds")
    click.echo(f"  {len(state.current_allocations)} final placements")


if __name__ == "__main__":
    main()
