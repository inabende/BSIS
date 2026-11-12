# Import Guide — Bringing in Existing Study Results

| | |
|---|---|
| **Version** | 0.1 |
| **Date** | 2026-11-11 |
| **For** | Project leads and system admins |

Use this to load results a study has kept in its own spreadsheets. Nothing is saved until you've seen a check of every row and confirmed.

**Where:** project page → **Import results** → **Import a file**.

## Before you start

- **One file = one smear type.** Put thick, thin and hematology results in separate files (or separate sheets of one workbook, imported one at a time).
- **One row = one slide's result.** Column names must be in one row (usually row 1).
- Make sure the project's **sites** are set up (Administration → Sites) and ticked on the project.
- Excel (.xlsx) or CSV, up to 10 MB / 20,000 rows. Old `.xls` files: open in Excel and *Save As* `.xlsx` first.
- No names or contact details: participant IDs only.
- Practise with **`docs/examples/example-legacy-thick-smears.xlsx`**, a typical study log. Three of its rows are deliberately wrong, so you can see how problems are reported.

## Step 1 — Upload

Choose the smear type and the file, and set:

| Option | Meaning |
|---|---|
| Sheet name | Excel only; blank = first sheet |
| Header row | The row with the column names |
| Dates written as | Day/month/year (default), month/day/year or year-month-day. Only matters for dates typed as text. |
| If a slide ID already exists | **Skip it** (best when re-importing an updated file) or treat it as an error |

## Step 2 — Match columns

The system guesses which column is which from the names. For example *Study No / PTID / Subject ID* → Participant ID, *BS for MPs / MPS / Result* → Result, and *Parasite density* → Parasite density as recorded. Check each match: the first values of the chosen column are shown beside it, so wrong matches stand out. Required: **Participant ID** and **Collection date** (plus **Result** for malaria smears).

Not in your file? Leave it as "not in this file":
- **Sample ID** → made from participant ID + collection date (e.g. `PT-001-20260915`)
- **Slide ID** → sample ID + `-TK` / `-TN` / `-HM`
- **Date read** → the collection date
- **Reader** → recorded as you

## Step 3 — Check rows

Every row is checked with the same rules as entering a result by hand. You'll see:

- **Ready to import:** rows that passed, with a preview of how the first ones will look.
- **Rows with problems:** each row number with what's wrong, e.g. *'31/02/2025' isn't a date*, *'Hospital X' isn't one of this project's sites*, *A negative slide can't have parasites counted*. Download the **problem report** to fix them in your file.
- **Warnings:** imported anyway, but worth knowing. Examples: a reader name that isn't a project reader, or a recorded density that differs from the one calculated from the counts.
- **Skipped:** slides already in the system.

Wrong matches? **Change column matches** and check again.

### What the checker understands

| Field | Accepted |
|---|---|
| Result | Positive, Pos, +, MPS seen · Negative, Neg, −, NMPS, No MPS seen, Nil |
| Species | Pf, P.f, P. falciparum, falciparum (and the same for vivax, malariae, ovale, knowlesi). Several: `Pf + Pm`, `Pf, Pm`, `Pf/Pm`. *Mixed* alone isn't enough; name the species. |
| Sex | F / M / U, Female / Male / Unknown |
| Yes/no fields | Yes, Y, 1, X, Present · No, N, 0, Absent, None |
| Dates | Real Excel dates, or text like 15/09/2026, 15-Sep-2026, 2026-09-15 |
| Numbers | 1200 or 1,200 |
| Blank | Empty, `-`, `NA`, `N/A` |

**Density-only files:** many old logs record only the density, not the parasite and WBC counts. Match that column to *Parasite density as recorded*, and positive rows are accepted without counts.

## Step 4 — Import

Click **Import N slides**. If some rows had problems, first tick the box confirming they'll be left out. Fix them in the file and import it again later: rows already imported are skipped automatically.

After import:
- Each slide has its **final result** straight away (single reader), marked *Imported from <file> (import #N)*. It still needs **approval by a reviewer** (Review queue).
- Each slide's page shows which import it came from. Every record's history says it was imported.
- The **original file** stays attached to the import (Import results → the import → *Original file*).

## Templates

For new data collection, **Import results → Templates** gives an Excel file per smear type with the right columns, two example rows, and a *How to fill this in* sheet listing allowed values and your project's site codes.
