#!/usr/bin/env python
"""Examples demonstrating key REAP allocation scenarios."""

from pathlib import Path
from seat_alloc import io_csv
from seat_alloc.category_priority import load as load_cp
from seat_alloc.rounds import run_simulation

data_dir = Path("data")

# Load data
seat_slots = io_csv.load_seat_matrix(data_dir / "seat_matrix.csv")
students = io_csv.load_students(data_dir / "students.csv")
ranks = io_csv.load_ranks(data_dir / "ranks.csv")
choices = io_csv.load_choices(data_dir / "choices.csv")
rank_idx = io_csv.build_rank_index(ranks)
choice_idx = io_csv.build_choice_index(choices)
priority = load_cp(data_dir / "category_priority.csv")
round_cfgs = io_csv.load_round_configs(data_dir / "rounds_config_betech.csv")

print("=" * 80)
print(" KEY ALLOCATION SCENARIOS IN REAP-2026".center(80))
print("=" * 80)

# Run simulation
state = run_simulation(students, choice_idx, rank_idx, seat_slots, priority, round_cfgs[:6])

print("\n" + "=" * 80)
print(" SCENARIO 1: Merit-First Rule (Reserved Candidate Gets GEN)".center(80))
print("=" * 80)

# Find an OBC student who got GEN
for app_no, alloc in state.current_allocations.items():
    student = state.student_map.get(app_no)
    if student and student.vertical_category.value == "OBC" and alloc.vertical and alloc.vertical.value == "GEN":
        ranks_student = rank_idx.get(app_no, {})
        print(f"\n✓ {app_no} ({student.name})")
        print(f"  Category: OBC | Gender: {student.gender.value}")
        print(f"  GEN rank: {ranks_student.get('GEN', 'N/A')} | OBC rank: {ranks_student.get('OBC', 'N/A')}")
        print(f"  ➜ Allocated: {alloc.institute_code}/{alloc.program_code} in {alloc.vertical.value} bucket")
        print(f"  💡 Despite being OBC, got GEN seat first (merit-first rule)")
        break

print("\n" + "=" * 80)
print(" SCENARIO 2: TFWS Supernumerary (Non-Mergeable)".center(80))
print("=" * 80)

tfws_allocs = [a for a in state.current_allocations.values() if a.supernumerary_kind]
if tfws_allocs:
    for alloc in tfws_allocs[:2]:
        student = state.student_map.get(alloc.application_no)
        if student:
            print(f"\n✓ {alloc.application_no} ({student.name})")
            print(f"  Family income: ₹{student.family_income:,.0f}")
            print(f"  ➜ Allocated: {alloc.institute_code}/{alloc.program_code} ({alloc.supernumerary_kind.value})")
            print(f"  💡 TFWS allotment is FINAL (cannot change institute/course)")

print("\n" + "=" * 80)
print(" SCENARIO 3: Horizontal Reservation (WOMEN)".center(80))
print("=" * 80)

women_allocs = [a for a in state.current_allocations.values()
                if a.horizontal and a.horizontal.value == "WOMEN"]
if women_allocs:
    for alloc in women_allocs[:2]:
        student = state.student_map.get(alloc.application_no)
        if student:
            print(f"\n✓ {alloc.application_no} ({student.name})")
            print(f"  Gender: {student.gender.value} | Category: {student.vertical_category.value}")
            ranks_student = rank_idx.get(alloc.application_no, {})
            cat_rank = f"{alloc.vertical.value}-WOMEN" if alloc.vertical else "GEN-WOMEN"
            print(f"  Rank in {cat_rank}: {ranks_student.get(cat_rank, 'N/A')}")
            print(f"  ➜ Allocated: {alloc.institute_code}/{alloc.program_code} in WOMEN sub-quota")

print("\n" + "=" * 80)
print(" SCENARIO 4: PwD Reservation".center(80))
print("=" * 80)

pwd_students = [s for s in students if s.is_pwd]
for student in pwd_students[:2]:
    alloc = state.current_allocations.get(student.application_no)
    if alloc:
        print(f"\n✓ {student.application_no} ({student.name})")
        print(f"  PwD: Yes | Category: {student.vertical_category.value}")
        ranks_student = rank_idx.get(student.application_no, {})
        pwd_cats = [k for k in ranks_student if "PWD" in k]
        print(f"  PwD ranks: {pwd_cats}")
        print(f"  ➜ Allocated: {alloc.institute_code}/{alloc.program_code}")
        h_str = f" ({alloc.horizontal.value} sub-quota)" if alloc.horizontal else " (general)"
        print(f"  Category: {alloc.category_token}{h_str}")

print("\n" + "=" * 80)
print(" SCENARIO 5: TSP Sub-Quota".center(80))
print("=" * 80)

tsp_students = [s for s in students if s.is_tsp_area_resident and s.vertical_category.value == "ST"]
for student in tsp_students[:2]:
    alloc = state.current_allocations.get(student.application_no)
    if alloc:
        print(f"\n✓ {student.application_no} ({student.name})")
        print(f"  ST category | TSP area resident: Yes")
        ranks_student = rank_idx.get(student.application_no, {})
        tsp_rank = ranks_student.get("ST-TSP", "N/A")
        print(f"  ST-TSP rank: {tsp_rank}")
        print(f"  ➜ Allocated: {alloc.institute_code}/{alloc.program_code}")
        tsp_str = f" (TSP sub-quota)" if alloc.tsp_subquota == "TSP" else ""
        print(f"  Category: {alloc.category_token}{tsp_str}")

print("\n" + "=" * 80)
print(" SCENARIO 6: Out of State (ORS) Candidate".center(80))
print("=" * 80)

ors_students = [s for s in students if not s.is_rajasthan_domicile]
for student in ors_students[:2]:
    alloc = state.current_allocations.get(student.application_no)
    if alloc:
        print(f"\n✓ {student.application_no} ({student.name})")
        print(f"  Domicile: {student.domicile_state}")
        print(f"  ➜ Allocated: {alloc.institute_code}/{alloc.program_code}")
        quota_str = f" ({alloc.state_quota.value})" if alloc.state_quota else ""
        print(f"  State quota: ORS (15% pool){quota_str}")

print("\n" + "=" * 80)
print(" All scenarios demonstrated successfully!".center(80))
print("=" * 80)
