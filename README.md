# Integrated Blood Smear System

One shared system where staff create projects (studies) and record blood smear results — malaria thick, malaria thin, general hematology, and custom smear types — so results are no longer kept in separate silos per study.

## Documentation

| Document | Contents |
|---|---|
| [docs/01-requirements.md](docs/01-requirements.md) | What the system must do: users, roles, requirements, open questions, implementation status |
| [docs/02-architecture.md](docs/02-architecture.md) | How it's built: components, technology, data model, web addresses, who-can-do-what, configuration, decisions |
| [docs/03-admin-guide.md](docs/03-admin-guide.md) | For system admins: smear types, adding custom types and fields |
| [CHANGELOG.md](CHANGELOG.md) | What changed in each phase |

Documents are living: each has a version and change log, updated as the system evolves.

## Roadmap

| Phase | Delivers | Status |
|---|---|---|
| 0 | Requirements and architecture | ✅ Done |
| 1 | Project setup, user accounts, projects, members and roles, participants, samples, change history | ✅ Done |
| 2 | Smear types and result entry (thick, thin, hematology, custom) with auto-calculations | ✅ Done |
| 3 | Reader 1/2, discordance flags, tie-breaker, locking | Next |
| 4 | Cross-project search, dashboards, Excel/CSV export | Not started |
| 5 | Excel/CSV import of existing study data | Not started |
| 6 | Production deployment, backups, login lockout, user guide | Not started |

## Running it on your computer (development)

Needs Python 3.12 or newer. From the project folder:

```bash
python -m venv .venv
```

```bash
.venv/Scripts/python -m pip install -r requirements.txt
```

```bash
.venv/Scripts/python manage.py migrate
```

Load demo data (sites, demo users, two projects with participants, samples and thick/thin smear results). The demo users' password is `DEMO_PASSWORD` in [apps/core/management/commands/seed_demo.py](apps/core/management/commands/seed_demo.py):

```bash
.venv/Scripts/python manage.py seed_demo
```

Or create your own admin account instead:

```bash
.venv/Scripts/python manage.py createsuperuser
```

Start the app, then open http://localhost:8000:

```bash
.venv/Scripts/python manage.py runserver
```

Run the automated tests:

```bash
.venv/Scripts/python manage.py test apps
```

On macOS/Linux, use `.venv/bin/python` instead of `.venv/Scripts/python`.

## First steps after logging in as an admin

1. **Administration → Sites:** add your laboratory and field sites.
2. **Administration → Users:** add staff. Tick *Can create projects* for anyone who should be able to start a project.
3. **Projects → New project:** create a study; you become its lead.
4. On the project page, **Add member** to give staff a role (lead, reader, reviewer, viewer).
5. **Register participant**, then **Add sample** from the participant's page.
6. On the sample's page, **Record smear result**: choose the smear type and its fields appear.

## Technology

Python, Django, PostgreSQL (SQLite for development), HTMX + Bootstrap. See the [architecture document](docs/02-architecture.md#2-technology-choices) for reasons.
