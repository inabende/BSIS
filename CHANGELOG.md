# Changelog

## Phase 4 — 2026-11-11

**Added**
- **Search** across all the user's projects: project(s), IDs, smear type, final result, species, QC status, site, collection dates, density range.
- **Export** of any search to Excel (final results sheet, one readings sheet per smear type with every field as a column, an About sheet with filters and definitions) or CSV (final results). Also from each project's results page.
- Exports leave out readings still being read blind (except for reviewers/admins), guard against spreadsheet formula injection, and are **logged** (Administration → Export logs).
- **Reports dashboard**: positivity, geometric mean density, reader disagreement rate, slides still being read, approved count; charts for positivity by project, monthly positivity, slides per month, species, density bands and disagreement by project, each with a data table; summary by project.
- Search and Reports in the top menu; guide for staff ([docs/05-search-reports-guide.md](docs/05-search-reports-guide.md)).
- Chart.js stored locally for offline use.
- 19 new automated tests (121 in total).

## Phase 3 — 2026-11-11

**Added**
- **Double reading:** each project sets 1 or 2 readers per smear type (QC settings). The setting is copied onto each slide when recorded.
- **Blind reading:** while a slide awaits reader 2 or a tie-breaker, readings are hidden from everyone but their own reader, reviewers and system admins: on the slide page, its history, edit pages and every results list. The same person can't read a slide twice.
- **Discordance checks:** positive vs negative, different species, or density/parasitaemia differing by more than the project's threshold (default 50% of the mean). Reasons are stored and shown.
- **Tie-breaker** (reader 3) for disagreeing slides, with a project choice of final rule: tie-breaker decides, or majority result with the mean of the two closest densities.
- **Final result** for every slide, showing how it was decided and which readings were used. Existing slides got one from their single reading.
- **Approval and locking** by data reviewers (one at a time or in bulk). Locked results can't be edited; unlocking needs a written reason, kept in history.
- **Review queue** per project: awaiting reader 2, awaiting tie-breaker, awaiting approval.
- "Needs attention" counts on the dashboard and project page.
- QC guide for staff ([docs/04-qc-guide.md](docs/04-qc-guide.md)).
- Demo data: MAL-2026-01 double-reads thick smears, with slides in every QC state.
- 38 new automated tests (102 in total).

**Changed**
- Results lists and sample pages show each slide's final result or QC status (never reader 1's reading directly). Result and species filters use final results; new status filter.

## Phase 2 — 2026-11-11

**Added**
- Smear types with configurable fields. Built in: malaria thick, malaria thin and general hematology. Admins can add custom types and fields without code changes ([admin guide](docs/03-admin-guide.md)).
- Each project chooses which smear types it records. New projects start with all built-in types.
- **Record smear result** page on each sample: choose the smear type and its fields load in place; slide and first reading are saved together. Slide IDs are suggested from the sample ID (e.g. `SM-001-TK`).
- Automatic calculations: thick smear parasite and gametocyte density (measured WBC/µL, else project default, else 8,000), thin smear parasitaemia %, hematology differential total.
- Consistency checks, e.g. a negative slide can't have parasites or species; infected RBCs can't exceed RBCs counted; the differential must total 100%; species required for a positive slide.
- Slide page showing each reading with its calculated values; edit slide and edit reading (recalculates); combined history of slide and readings, listing each changed result field.
- Project **Smear results** list, filterable by smear type, result and species.
- Demo data now includes thick and thin results.
- 30 new automated tests (64 in total).

**Changed**
- Sample page lists its slides and results.
- Project page shows a smear results count and the project's smear types.
- Forms show units beside number fields and mark "required if positive" fields.

## Phase 1 — 2026-11-11

**Added**
- Django project setup with settings driven by environment variables (SQLite in development, PostgreSQL ready for production).
- User accounts with login, logout, password change and 30-minute inactivity timeout. Accounts can be deactivated but not deleted.
- Sites (managed by system admins).
- Projects: create, edit, change status (active / closed / archived, with a reason), members with roles (lead, reader, reviewer, viewer).
- Participants (study ID only, plus optional sex, year of birth, enrolment site and date) and samples (sample ID, visit, collection time, site).
- One central set of permission rules, with a project always keeping at least one lead.
- Full change history on every record, with a History page showing who changed what and when.
- Dashboard with totals, active projects and recently recorded samples.
- `seed_demo` command for demo/training data.
- 34 automated tests covering permissions, project management, participants and samples.

## Phase 0 — 2026-11-11

**Added**
- Requirements specification and system architecture documents.
