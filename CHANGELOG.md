# Changelog

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
