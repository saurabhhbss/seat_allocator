# REAP-2026 Seat Allocation Simulator

A Python-based seat allocation simulator that implements the REAP-2026 (Rajasthan Engineering Admission Process) rules, including:

- Choice-first Gale-Shapley allocation with configurable category priority
- Progressive horizontal merging (WOMEN after Round 1, PWD/EXS after Round 2)
- Multi-round simulation (TFWS, Special, Main, Upward, Internal Sliding, Direct+Management)
- Non-mergeable supernumerary seats (TFWS/KM/Foreign-OCI)
- TSP sub-quota within ST vertical
- RSQ (85%) and ORS (15%) state quota split
- 5-status reporting workflow

## Quick Start

### Option 1: One-Click Launch (Recommended)

**Linux/Mac:**
```bash
./run.sh
```

**Windows:**
```
run.bat
```

This will:
1. Create a virtual environment (if needed)
2. Install dependencies
3. Open the Streamlit UI in your browser

### Option 2: Manual Setup

```bash
# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install
pip install -e .

# Launch UI
seat ui

# Or run headlessly
seat run --data data --out results
```

## Input Files (All CSV)

All input files live in the `data/` directory and can be edited in Excel or Google Sheets.

### Required Files

1. **`seat_matrix.csv`** - Seat counts per bucket

| Column | Description | Example |
|--------|-------------|---------|
| `institute_code` | Institute ID | `GOVT01` |
| `program_code` | Program/branch code | `CSE` |
| `seat_type` | `GAS` (Govt Aided) or `SFS` (Self Finance) | `GAS` |
| `state_quota` | `RSQ` (Rajasthan) or `ORS` (Out of State) | `RSQ` |
| `vertical` | `GEN`, `SC`, `ST`, `OBC`, `MBC`, `EWS` | `SC` |
| `horizontal` | `WOMEN`, `PWD`, `EXS`, `EXS_GIRLS` (or blank) | `WOMEN` |
| `tsp_subquota` | `TSP`, `NON_TSP` (or blank) | `TSP` |
| `capacity` | Number of seats | `10` |
| `is_supernumerary` | `yes` or `no` | `no` |
| `supernumerary_kind` | `TFWS`, `KM`, `FOREIGN_OCI`, etc. (or blank) | `TFWS` |

2. **`students.csv`** - Student profiles

| Column | Description | Example |
|--------|-------------|---------|
| `application_no` | Unique student ID | `S001` |
| `name` | Student name | `Amit Sharma` |
| `programme` | `BE_BTECH_BPLAN` or `BARCH` | `BE_BTECH_BPLAN` |
| `vertical_category` | `GEN`, `SC`, `ST`, `OBC`, `MBC`, `EWS` | `OBC` |
| `gender` | `MALE`, `FEMALE`, `OTHER` | `FEMALE` |
| `is_pwd` | Person with Disability (yes/no) | `no` |
| `exs_code` | Ex-Servicemen code: `EXS1`-`EXS9` (or blank) | `EXS6` |
| `domicile_state` | State of domicile | `RAJASTHAN` |
| `is_tsp_area_resident` | TSP area resident (yes/no) | `yes` |
| `is_kashmiri_migrant` | Kashmiri Migrant (yes/no) | `no` |
| `family_income` | Annual family income (for TFWS) | `600000` |

3. **`ranks.csv`** - Pre-computed ranks per category

| Column | Description | Example |
|--------|-------------|---------|
| `application_no` | Student ID | `S001` |
| `category` | Category token (see below) | `OBC-WOMEN` |
| `rank` | Rank in that category | `55` |

**Valid category tokens:**
- Verticals: `GEN`, `SC`, `ST`, `OBC`, `MBC`, `EWS`
- Vertical + Horizontal: `GEN-WOMEN`, `SC-PWD`, `OBC-EXS`, etc.
- TSP: `ST-TSP`, `ST-TSP-WOMEN`, etc.
- Supernumerary: `TFWS`, `KM`, `FOREIGN_OCI`, `WORKING_PROF`

Each student has one row per category they qualify for (including all horizontal combinations).

4. **`choices.csv`** - Student preferences

| Column | Description | Example |
|--------|-------------|---------|
| `application_no` | Student ID | `S001` |
| `preference_order` | 1, 2, 3, ... (higher = more preferred) | `1` |
| `institute_code` | Institute ID | `GOVT01` |
| `program_code` | Program/branch code | `CSE` |

### Configuration Files

5. **`category_priority.csv`** - Configurable priority order

Defines the order in which seat buckets are tried for each vertical category:

| vertical | priority_order |
|----------|----------------|
| `GEN` | `GEN,GEN-WOMEN,GEN-PWD,GEN-EXS` |
| `SC` | `GEN,GEN-WOMEN,GEN-PWD,GEN-EXS,SC,SC-WOMEN,SC-PWD,SC-EXS` |
| ... | ... |

6. **`rounds_config_betech.csv`** / **`rounds_config_barch.csv`**

Defines the round schedule (10 rounds for B.E./B.Tech, 8 for B.Arch).

| Column | Description |
|--------|-------------|
| `round_no` | 0, 1, 2, ... |
| `name` | "TFWS Counseling", "Special Categories", etc. |
| `mode` | `mock`, `fresh`, `upward`, `sliding`, `spot` |
| `eligible_filter` | `all`, `is_tfws_eligible`, `is_rajasthan_domicile`, etc. |
| `requires_reported` | `yes` or `no` |
| `rank_list` | `main` or `tfws` (separate TFWS rank list) |
| `merge_after` | `WOMEN`, `PWD,EXS`, `ORS` (or blank) |

Optional config files (defaults provided if missing):
- `reservation_config.csv` - Vertical percentages (SC 16%, ST 12%, etc.)
- `horizontal_config.csv` - Horizontal percentages (WOMEN 30%, PWD 5%, EXS 3%)
- `state_quota_config.csv` - RSQ 85% / ORS 15%
- `tsp_config.csv` - TSP 45% of ST
- `supernumerary.csv` - TFWS 5%, KM 5%, Foreign/OCI 15%
- `exs_priority.csv` - 9-level Ex-Servicemen priority codes

## How It Works

### Allocation Algorithm (Choice-First)

For each student (sorted by best applicable rank):
1. Try their **1st choice** with all eligible category ranks (GEN first, then reserved)
2. If placed, stop; else try **2nd choice** with all categories
3. Continue until placed or all choices exhausted

Displaced students re-enter the queue from their next untried slot.

### Progressive Horizontal Merging

**Round 1 (Pass 1):** Allocate with all sub-quotas active (WOMEN, PWD, EXS).
- **After Round 1:** Unfilled WOMEN seats merge into their parent vertical

**Round 2 (Pass 2):** Re-allocate on updated matrix.
- **After Round 2:** Unfilled PWD and EXS seats merge into their parent vertical

**Round 3+:** Allocate on fully merged matrix (no horizontal sub-quotas remain).

### Supernumerary Handling

TFWS, KM, Foreign/OCI, Working Professional seats are:
- Processed in **separate dedicated rounds**
- **NEVER merged** into general pool if unfilled
- Left vacant if no eligible candidates

## Reservation Rules (REAP-2026)

### Vertical Reservations (within RSQ 85%)
- SC: 16%
- ST: 12%
- OBC-NCL: 21%
- MBC-NCL: 5%
- EWS: 10%
- GEN: remainder (~36%)

### Horizontal Reservations (within each vertical)
- Women: 30%
- PwD (>=40% disability): 5%
- Ex-Servicemen: 3% (50% reserved for girls)
- TSP: 45% of ST in TSP-area institutes

### Merit-First Rule

Reserved-category candidates qualifying for GEN by rank are allocated GEN seats first, preserving reserved seats for lower-rank reserved candidates.

## Output Files

After running the allocation:

- **`round_summary.csv`** - Per-round statistics
- **`allocations.csv`** - All allocations across all rounds
- **`final_allocations.csv`** - Final placements after last round
- **`cutoffs.csv`** - Opening and closing ranks per (institute, program, category)
- **`vacancies.csv`** - Seat-wise capacity vs filled vs vacant

All can be downloaded as Excel from the UI.

## Streamlit UI

The UI provides a 5-step wizard:

1. **Load Data** - Upload or use sample CSVs
2. **Edit Data** - In-browser spreadsheet editors for all files
3. **Reservation Policy** - Edit category priority and reservation percentages
4. **Run Allocation** - Choose programme and run simulation
5. **Results** - View allocations, cutoffs, vacancies; download as Excel

## CLI Commands

```bash
seat ui                    # Launch Streamlit UI (default)
seat run --data DIR        # Headless run, write results to out/
```

## Sample Data

The bundled `data/` folder contains:
- 3 institutes (govt, private, TSP-area)
- 5 programs (CSE, ECE, ME, CE)
- 40 students spanning all verticals, genders, horizontals (PwD, EXS), TSP, KM
- 3-round demo config

## Customization

All allocation behavior is CSV-driven:

- **Change merit-first priority?** Edit `category_priority.csv` (e.g., make SC try SC before GEN)
- **Add a round?** Add a row to `rounds_config_*.csv`
- **Change reservation percentages?** Edit `reservation_config.csv`
- **Adjust merging schedule?** Change `merge_after` column in round configs

## Technical Stack

- **Python 3.13**
- **pandas** - CSV/Excel I/O
- **pydantic** - Validation
- **streamlit** - Web UI
- **click** - CLI

## License

This is a simulation tool for educational and planning purposes.  
It implements the REAP-2026 rules as documented in the official booklet.

## Support

For issues or questions, check:
- Input file column names match the tables above
- All required files are present
- Validation errors show row/column hints

The UI displays plain-English error messages if data is malformed.
