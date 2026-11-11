# Changelog

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
