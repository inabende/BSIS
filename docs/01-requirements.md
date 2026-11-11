# Requirements Specification — Integrated Blood Smear System

| | |
|---|---|
| **Version** | 0.5 (draft) |
| **Date** | 2026-11-11 |
| **Status** | Living document — updated as the system evolves |

## 1. Purpose

Blood smear results are currently stored separately by each study/project. This makes it hard to find past results, compare across studies, or reuse data for future reference.

This system provides **one shared place** where staff can create projects and record blood smear results, while keeping each project's data organised and access-controlled.

## 2. Scope

**In scope (version 1)**
- Projects (studies), participants, samples, and smear results
- Smear types: malaria thick, malaria thin, general hematology, and admin-defined custom types
- Multiple readers per slide with discordance flagging
- Search and export across projects
- User accounts, roles and an audit trail
- Import of existing results from Excel/CSV

**Out of scope (for now)**
- Direct connection to microscopes or digital slide scanners
- Image storage of slides (may be added later)
- Integration with external LIMS/EMR systems (may be added later)

## 3. Users and roles

| Role | Can do |
|---|---|
| **System admin** | Manage users, smear types and fields, all projects, system settings |
| **Project lead** | Create/edit their projects, choose allowed smear types, assign project members |
| **Lab reader** | Register samples and enter smear readings for projects they belong to |
| **Data reviewer** | Review discordant readings, approve/lock results |
| **Viewer** | Read-only access to projects they are given access to |

A user can hold different roles in different projects.

## 4. Functional requirements

### 4.1 Projects
- **FR-1** A project lead can create a project with: name, short code, protocol/ethics ID, principal investigator, site(s), start/end date, description.
- **FR-2** Each project selects which smear types it allows (e.g. only malaria thick + thin).
- **FR-3** Projects can be marked active, closed, or archived. Closed projects are read-only.

### 4.2 Participants and samples
- **FR-4** Register participants within a project using the study's participant ID (unique per project). No names are required.
- **FR-5** Record samples per participant: sample ID, visit/timepoint, collection date and time, site.
- **FR-6** One sample can have several smears (e.g. a thick and a thin slide from the same draw).

### 4.3 Smear results
- **FR-7** When recording a result, the user chooses the **smear type**; the form shows only that type's fields.
- **FR-8** Built-in smear types and their fields:

  | Smear type | Fields |
  |---|---|
  | Malaria – thick | Result (positive/negative), species, asexual parasites counted, WBCs counted, assumed or measured WBC/µL, parasite density (auto-calculated), gametocytes present, gametocytes counted |
  | Malaria – thin | Species, RBCs counted, infected RBCs, parasitaemia % (auto-calculated), stages seen (rings, trophozoites, schizonts, gametocytes) |
  | General hematology | Differential count (neutrophils, lymphocytes, monocytes, eosinophils, basophils, band forms), RBC morphology, WBC comments, platelet estimate/comments |

- **FR-9** System admins can create new smear types and add fields (text, number, choice, multi-choice, yes/no, date) without code changes.
- **FR-10** Calculated values:
  - Thick smear density (parasites/µL) = parasites counted ÷ WBCs counted × WBC/µL (default 8,000, configurable per project).
  - Thin smear parasitaemia % = infected RBCs ÷ RBCs counted × 100.
- **FR-11** Each result records slide ID, reader, reading date, microscope/site and free-text comments.

### 4.4 Multiple readers and quality control
- **FR-12** A slide can be read by Reader 1 and Reader 2 independently (readers can't see each other's result until both are entered).
- **FR-13** The system flags discordance when readers differ on positive/negative, species, or density beyond a configurable threshold (default: more than 50% difference).
- **FR-14** Discordant slides are sent for a tie-breaker (third) reading; the final result follows a project-configurable rule (e.g. tie-breaker decides, or the two closest readings are averaged).
- **FR-15** A data reviewer can approve and lock final results. Locked results can only be changed with a stated reason.

### 4.5 Search, reporting and export
- **FR-16** Search across all projects the user can access, filtered by project, smear type, species, result, date range, site and participant.
- **FR-17** Summary dashboards: counts by project, positivity rate, species distribution, discordance rate.
- **FR-18** Export search results to Excel/CSV.

### 4.6 Import
- **FR-19** Import existing results from Excel/CSV into a project, with column mapping, validation and a preview before saving.
- **FR-20** The import reports rows that failed validation and why.

### 4.7 Users and audit
- **FR-21** Users log in with username and password. Accounts can be deactivated, never deleted.
- **FR-22** Every create, change and delete of project, sample or result data is recorded in an audit trail: who, when, what changed (old → new), and why (when required).

## 5. Non-functional requirements

| ID | Requirement |
|---|---|
| **NFR-1 Access** | Browser-based; works on Chrome, Edge and Firefox on lab PCs and tablets |
| **NFR-2 Network** | Runs on the local network; no internet connection required for daily use |
| **NFR-3 Security** | Role-based access per project; passwords stored hashed; session timeout; HTTPS on the local network |
| **NFR-4 Privacy** | Stores study participant IDs only, no personal identifiers by default |
| **NFR-5 Data integrity** | Validation on all inputs (e.g. counts can't be negative; WBC counted > 0 for density) |
| **NFR-6 Audit** | Audit trail can't be edited by any user, including admins |
| **NFR-7 Backup** | Automated daily database backup with a documented restore procedure |
| **NFR-8 Performance** | Search across 1 million results returns in under 3 seconds |
| **NFR-9 Maintainability** | Documented code and architecture; widely used open-source stack |

## 6. Open questions

These will be settled as we build:

1. How many staff and sites will use it, and how many concurrently?
2. Final discordance thresholds and tie-breaker rules — standard for all, or per project?
3. Should participant data be shared across projects (same person enrolled in two studies)?
4. Does any project require compliance with a specific standard (e.g. GCLP, 21 CFR Part 11 e-signatures)?
5. Formats of existing per-study spreadsheets to be imported.
6. Should slide images be stored in a later version?
7. At very low densities a small absolute difference is a large percentage (e.g. 16 vs 40/µL = 86%). Should the density check only apply above a minimum density, or use a different method (e.g. log ratio)?
8. Hematology double readings aren't compared automatically (there's no positive/negative). Should differential counts be compared, and with what tolerance?
9. Should project leads also be able to approve and lock results, or only data reviewers (current setting)?
10. Should exports be restricted to certain roles (currently any project member can export what they can see; every export is logged)?
11. NFR-8 (search over 1 million results in under 3 seconds) hasn't been load-tested yet; it should be checked on PostgreSQL before go-live.

## 7. Implementation status

| Requirement | Status | Phase |
|---|---|---|
| FR-1 Create projects | ✅ Done | 1 |
| FR-2 Allowed smear types per project | ✅ Done (new projects start with all built-in types ticked) | 2 |
| FR-3 Active / closed / archived | ✅ Done (status change needs a reason; only admins reopen) | 1 |
| FR-4 Participants by study ID | ✅ Done (plus optional sex, year of birth, enrolment site and date) | 1 |
| FR-5 Samples per participant | ✅ Done | 1 |
| FR-6 Several smears per sample | ✅ Done | 2 |
| FR-7 Choose smear type, form shows its fields | ✅ Done (fields swap in place when the type changes) | 2 |
| FR-8 Built-in thick, thin, hematology fields | ✅ Done (plus fields examined, gametocyte density, RBC morphology list, incidental parasites) | 2 |
| FR-9 Admin-defined smear types and fields | ✅ Done via Administration → Smear types; see [03-admin-guide.md](03-admin-guide.md) | 2 |
| FR-10 Calculations | ✅ Done, plus consistency checks (e.g. negative slide with parasites, differential ≠ 100%) | 2 |
| FR-11 Slide ID, reader, date, microscope/site, comments | ✅ Done | 2 |
| FR-12 Independent, blinded reader 1 and 2 | ✅ Done; readers required set per smear type per project; the same person can't read a slide twice | 3 |
| FR-13 Discordance flags with configurable threshold | ✅ Done (difference as % of the two readings' mean; default 50%) | 3 |
| FR-14 Tie-breaker and final-result rule | ✅ Done: "tie-breaker decides" or "majority, mean of the two closest" | 3 |
| FR-15 Reviewer approves and locks; unlock needs a reason | ✅ Done, including bulk approval from a review queue | 3 |
| FR-16 Search across projects | ✅ Done: project(s), smear type, result, species, QC status, site, collection dates, density range, IDs | 4 |
| FR-17 Summary dashboards | ✅ Done: positivity, geometric mean density, species, density bands, monthly trend, reader disagreement, by project | 4 |
| FR-18 Export to Excel/CSV | ✅ Done: final results + per-smear-type readings sheets + filters/metadata sheet; every export logged | 4 |
| FR-19 – FR-20 Import | Planned | 5 |
| FR-21 Accounts, deactivate not delete | ✅ Done | 1 |
| FR-22 Audit trail | ✅ Done for all Phase 1 records, with a History page on each | 1 |
| NFR-3 Session timeout, password rules | ✅ Done; login lockout planned | 1 / 6 |

## 8. Change log

| Version | Date | Change |
|---|---|---|
| 0.1 | 2026-11-11 | Initial draft from first design discussion |
| 0.2 | 2026-11-11 | Added implementation status after Phase 1 |
| 0.3 | 2026-11-11 | Phase 2 status: smear types, result entry, calculations |
| 0.4 | 2026-11-11 | Phase 3 status: double reading, discordance, tie-breaker, locking; open questions 7–9 |
| 0.5 | 2026-11-11 | Phase 4 status: cross-project search, dashboards, exports; open questions 10–11 |
