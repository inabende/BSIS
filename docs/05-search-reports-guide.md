# Search, Reports and Export Guide

| | |
|---|---|
| **Version** | 0.1 |
| **Date** | 2026-11-11 |
| **For** | Everyone, especially data managers, statisticians and PIs |

Search, Reports and Export cover **all the projects you're a member of**, in one place. You never see projects you don't belong to.

## Search (top menu → Search)

Filter by any combination of:

| Filter | Notes |
|---|---|
| Projects | Pick one or several (Ctrl/Cmd-click). None picked = all your projects. |
| Slide, sample or participant ID | Part of an ID is enough |
| Smear type, result, species | Result and species use each slide's **final** result after quality control |
| Status | Awaiting reader 2 · awaiting tie-breaker · final not yet approved · approved and locked · has a final result |
| Site | Where the sample was collected |
| Collected from / to | Sample collection dates |
| Density from / to | Final parasite density (/µL) |

Slides still being read show their status instead of a result. This keeps blind reading intact.

## Export (Search → Export to Excel / CSV)

Exports contain exactly the slides your search found. A project's **Smear results** page also has export buttons for that project.

**Excel** workbook:

| Sheet | Contents |
|---|---|
| Final results | One row per slide: project, participant (ID, sex, year of birth), sample, visit, collection date and site, slide, smear type, stain, QC status, final result, species, density, parasitaemia, how it was decided, whether readers disagreed and why, approval details |
| *Smear type* readings (e.g. *Malaria – thick smear readings*) | One row per reading, with **every field of that smear type as its own column** (e.g. parasites counted, WBCs counted, gametocytes, stages, differential counts) |
| About | Who exported, when, the filters used, and what the columns mean |

**CSV** contains the *Final results* table only.

Good to know:
- Readings of slides still being read blind are **left out**, unless you're a reviewer or system admin for that project.
- Every export is **logged** (who, when, filters, projects, row counts). System admins can see the log under Administration → Export logs.
- Dates and times are in the server's local time.

## Reports (top menu → Reports)

Uses the same filters, for **one smear type at a time** (default: malaria thick smear), so a thick and a thin slide from the same sample aren't counted twice.

| Figure | Meaning |
|---|---|
| Slides with a final result | Slides that have finished reading (approved or not) |
| Positivity | Positive ÷ (positive + negative) final results |
| Geometric mean density | Typical density among positive slides. The geometric mean suits skewed parasite counts better than the ordinary average. |
| Readers disagreed | % of double-read slides where readers 1 and 2 disagreed |
| Still being read | Awaiting reader 2 or a tie-breaker (no final result yet) |
| Approved and locked | Final results approved by a reviewer |

Charts: positivity by project, monthly positivity, slides per month, species among positives, parasite density bands, and reader disagreement by project. Hover over a bar or point for exact numbers, or open **Show data** under any chart for the table. A summary table by project is at the bottom.

Use **See these slides** to jump from a report to the matching slides in Search, and **Reports for these filters** to go the other way.
