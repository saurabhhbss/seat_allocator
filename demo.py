#!/usr/bin/env python
"""Demonstration of the REAP-2026 Seat Allocator.

Shows how the choice-first algorithm works with progressive horizontal merging.
"""

from pathlib import Path
from seat_alloc import io_csv
from seat_alloc.category_priority import load as load_cp
from seat_alloc.rounds import run_simulation
from seat_alloc.reports import allocation_table, per_round_summary, cutoff_table, vacancy_table

data_dir = Path("data")

print("=" * 70)
print(" REAP-2026 SEAT ALLOCATION SIMULATOR - DEMO".center(70))
print("=" * 70)

# Load data
print("\nLoading sample data...")
seat_slots = io_csv.load_seat_matrix(data_dir / "seat_matrix.csv")
students = io_csv.load_students(data_dir / "students.csv")
ranks = io_csv.load_ranks(data_dir / "ranks.csv")
choices = io_csv.load_choices(data_dir / "choices.csv")

print(f"  {len(students)} students")
print(f"  {len(seat_slots)} seat slots across 3 institutes")
print(f"  {len(set(c.institute_code + '/' + c.program_code for c in choices))} unique programs")

# Build indices
rank_idx = io_csv.build_rank_index(ranks)
choice_idx = io_csv.build_choice_index(choices)
priority = load_cp(data_dir / "category_priority.csv")

# Load round configs
round_cfgs = io_csv.load_round_configs(data_dir / "rounds_config_betech.csv")

print(f"\nRunning {len(round_cfgs)} rounds...")
print("-" * 70)

# Run simulation
state = run_simulation(students, choice_idx, rank_idx, seat_slots, priority, round_cfgs)

# Display results
print("\n" + "=" * 70)
print(" ALLOCATION RESULTS".center(70))
print("=" * 70)

summary = per_round_summary(state)
print("\n🔄 Per-Round Summary:")
print(summary.to_string(index=False))

print("\n" + "=" * 70)
print(f"\n✅ Final Placement Summary:")
print(f"   Total placed: {len(state.current_allocations)} / {len(students)}")
print(f"   Unplaced: {len(students) - len(state.current_allocations)}")

# Category breakdown
from collections import Counter
cats = Counter(a.category_token for a in state.current_allocations.values())
print(f"\n📊 Placements by Category:")
for cat, count in sorted(cats.items()):
    print(f"   {cat:20s}: {count:3d} students")

# Institute breakdown
insts = Counter(a.institute_code for a in state.current_allocations.values())
print(f"\n🏛️  Placements by Institute:")
for inst, count in sorted(insts.items()):
    print(f"   {inst:20s}: {count:3d} students")

# Cutoffs
print("\n" + "=" * 70)
print(" CUTOFF RANKS (Top 10)".center(70))
print("=" * 70)
cutoffs = cutoff_table(state)
print(cutoffs.head(10).to_string(index=False))

# Vacancies
print("\n" + "=" * 70)
print(" SEAT VACANCIES".center(70))
print("=" * 70)
vacancies = vacancy_table(state.seat_slots, state.current_allocations)
vacant = vacancies[vacancies["vacant"] > 0].sort_values("vacant", ascending=False)
if not vacant.empty:
    print(vacant[["institute_code", "program_code", "category", "capacity", "filled", "vacant"]].head(15).to_string(index=False))
else:
    print("  All seats filled!")

total_cap = vacancies["capacity"].sum()
total_filled = vacancies["filled"].sum()
print(f"\n📈 Overall Fill Rate: {total_filled}/{total_cap} ({100 * total_filled / total_cap:.1f}%)")

print("\n" + "=" * 70)
print(" DEMO COMPLETE".center(70))
print("=" * 70)
print("\n💡 To explore interactively, run: ./run.sh or seat ui")
print("📁 Results can be exported as CSV/Excel from the Streamlit UI")
