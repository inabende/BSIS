"""
Load demo data for development and training.

    python manage.py seed_demo

Creates sites, demo users, two projects, participants and samples.
FOR DEVELOPMENT ONLY. Never run this on the production server.

All demo users share the password in DEMO_PASSWORD below.
"""

from datetime import date, timedelta
from decimal import Decimal

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.projects.models import Project, ProjectMembership, Site
from apps.samples.models import Participant, Sample

DEMO_PASSWORD = "demo-pass-2026"

# username, first, last, job title, superuser, can create projects
DEMO_USERS = [
    ("admin", "System", "Admin", "Data manager", True, True),
    ("lead", "Grace", "Lead", "Principal investigator", False, True),
    ("reader1", "Peter", "Reader", "Microscopist", False, False),
    ("reader2", "Ruth", "Reader", "Microscopist", False, False),
    ("reviewer", "Alex", "Reviewer", "QA officer", False, False),
    ("viewer", "Sam", "Viewer", "Statistician", False, False),
]

Role = ProjectMembership.Role

# Thick + thin result patterns cycled across demo samples:
# (positive, species, asexual per 200 WBC, gametocytes, infected RBC per 2000)
DEMO_PATTERNS = [
    (False, [], 0, 0, 0),
    (True, ["pf"], 152, 0, 41),
    (False, [], 0, 0, 0),
    (True, ["pf"], 18, 3, 6),
    (True, ["pf", "pm"], 64, 0, 15),
    (False, [], 0, 0, 0),
    (True, ["pv"], 9, 2, 3),
]


class Command(BaseCommand):
    help = "Load demo data (development only)."

    def add_arguments(self, parser):
        parser.add_argument("--force", action="store_true", help="Run even when DEBUG is off.")

    def add_demo_results(self, project, users):
        """Thick and thin smear readings for each demo sample that has no slides yet."""
        from apps.smears.calculations import calculate
        from apps.smears.models import ProjectSmearType, Reading, Slide, SmearType

        thick = SmearType.objects.get(code="malaria_thick")
        thin = SmearType.objects.get(code="malaria_thin")
        for smear_type in SmearType.objects.filter(is_builtin=True):
            ProjectSmearType.objects.get_or_create(project=project, smear_type=smear_type)

        samples = project.samples.filter(slides__isnull=True).order_by("collected_at")
        for index, sample in enumerate(samples):
            positive, species, asexual, gametocytes, infected = DEMO_PATTERNS[index % len(DEMO_PATTERNS)]
            reader = users["reader1"] if index % 2 else users["reader2"]
            read_at = sample.collected_at + timedelta(hours=6)
            if positive:
                thick_values = {"result": "positive", "species": species, "asexual_parasites_counted": asexual,
                                "wbc_counted": 200, "gametocytes_present": bool(gametocytes)}
                if gametocytes:
                    thick_values["gametocytes_counted"] = gametocytes
                thin_values = {"result": "positive", "species": species, "rbc_counted": 2000,
                               "infected_rbc": infected, "stages": ["rings"] + (["gametocytes"] if gametocytes else [])}
            else:
                thick_values = {"result": "negative", "fields_examined": 100, "gametocytes_present": False}
                thin_values = {"result": "negative", "fields_examined": 100}

            for smear_type, values in ((thick, thick_values), (thin, thin_values)):
                slide = Slide.objects.create(
                    sample=sample, smear_type=smear_type, slide_id=f"{sample.sample_id}-{smear_type.slide_suffix}",
                    status=Slide.Status.FINAL, prepared_on=sample.collected_at.date(), created_by=reader,
                )
                results = calculate(smear_type, values, project)
                Reading.objects.create(
                    slide=slide, reader=reader, read_at=read_at, site=sample.site, created_by=reader,
                    values={**values, **{k: float(v) if hasattr(v, "quantize") else v
                                         for k, v in results["derived"].items()}},
                    is_positive=results["is_positive"], species=results["species"],
                    density_per_ul=results["density_per_ul"], parasitaemia_pct=results["parasitaemia_pct"],
                )

    def add_demo_double_reading(self, project, users):
        """
        MAL-2026-01 double-reads thick smears. Gives its single-read thick slides a
        second reading, so the demo has slides in every QC state.
        """
        from apps.qc.models import FinalResult
        from apps.qc.services import evaluate_slide
        from apps.qc.views import lock_final
        from apps.smears.models import ProjectSmearType, Reading, Slide

        ProjectSmearType.objects.filter(project=project, smear_type__code="malaria_thick").update(readers_required=2)
        slides = (
            Slide.objects.filter(project=project, smear_type__code="malaria_thick", readers_required=1)
            .order_by("sample__collected_at")
        )
        for index, slide in enumerate(slides):
            r1 = slide.readings.get(reader_number=1)
            slide.readers_required = 2
            slide.save(update_fields=["readers_required"])
            FinalResult.objects.filter(slide=slide, locked=False).delete()
            other = users["reader1"] if r1.reader_id == users["reader2"].pk else users["reader2"]
            state = index % 8
            if state == 7:  # awaiting reader 2
                evaluate_slide(slide)
                continue

            r2 = Reading(slide=slide, reader_number=2, reader=other, read_at=r1.read_at + timedelta(hours=2),
                         site=r1.site, created_by=other, values=dict(r1.values))
            for field in ("is_positive", "species", "density_per_ul", "parasitaemia_pct"):
                setattr(r2, field, getattr(r1, field))
            if state in (2, 5) and r1.is_positive:  # density disagreement
                r2.density_per_ul = r1.density_per_ul * 3
                r2.values["asexual_parasites_counted"] = r1.values.get("asexual_parasites_counted", 0) * 3
            elif state in (2, 5):  # reader 2 calls a negative slide positive
                r2.is_positive, r2.species, r2.density_per_ul = True, "pf", 80
                r2.values = {"result": "positive", "species": ["pf"], "asexual_parasites_counted": 2,
                             "wbc_counted": 200, "wbc_per_ul_used": 8000}
            elif r1.is_positive:  # small, acceptable difference
                r2.density_per_ul = r1.density_per_ul * Decimal("1.1")
            r2.save()

            if state == 5:  # tie-breaker by the lead, agreeing with reader 1
                r3 = Reading(slide=slide, reader_number=3, reader=users["lead"], read_at=r1.read_at + timedelta(days=1),
                             site=r1.site, created_by=users["lead"], values=dict(r1.values))
                for field in ("is_positive", "species", "density_per_ul", "parasitaemia_pct"):
                    setattr(r3, field, getattr(r1, field))
                r3.save()

            final = evaluate_slide(slide)
            if final and state in (0, 1, 3):
                lock_final(final, users["reviewer"])

    @transaction.atomic
    def handle(self, *args, **options):
        if not settings.DEBUG and not options["force"]:
            raise CommandError("DEBUG is off — this looks like production. Use --force to override.")

        sites = {
            code: Site.objects.get_or_create(code=code, defaults={"name": name, "location": loc})[0]
            for code, name, loc in [
                ("MAIN", "Main Laboratory", "Headquarters"),
                ("FLD1", "Field Clinic 1", "District A"),
                ("FLD2", "Field Clinic 2", "District B"),
            ]
        }

        users = {}
        for username, first, last, title, superuser, can_create in DEMO_USERS:
            user, created = User.objects.get_or_create(
                username=username,
                defaults={
                    "first_name": first,
                    "last_name": last,
                    "job_title": title,
                    "is_superuser": superuser,
                    "is_staff": superuser,
                    "can_create_projects": can_create,
                },
            )
            if created:
                user.set_password(DEMO_PASSWORD)
                user.save()
            users[username] = user

        projects = [
            ("MAL-2026-01", "Malaria Vaccine Efficacy Trial", "PROT-0412", [sites["MAIN"], sites["FLD1"]]),
            ("IPT-2025-03", "Intermittent Preventive Treatment Cohort", "PROT-0388", [sites["FLD1"], sites["FLD2"]]),
        ]
        now = timezone.now()
        for index, (code, name, protocol, project_sites) in enumerate(projects):
            project, created = Project.objects.get_or_create(
                code=code,
                defaults={
                    "name": name,
                    "protocol_id": protocol,
                    "principal_investigator": "Dr Grace Lead",
                    "start_date": date(2025 + (1 - index), 1, 15),
                    "created_by": users["lead"],
                },
            )
            if not created:
                continue
            project.sites.set(project_sites)
            for username, role in [
                ("lead", Role.LEAD),
                ("reader1", Role.READER),
                ("reader2", Role.READER),
                ("reviewer", Role.REVIEWER),
                ("viewer", Role.VIEWER),
            ]:
                ProjectMembership.objects.create(project=project, user=users[username], role=role)

            for n in range(1, 9):
                site = project_sites[n % len(project_sites)]
                participant = Participant.objects.create(
                    project=project,
                    study_participant_id=f"{code[:3]}-{n:04d}",
                    sex=["F", "M"][n % 2],
                    year_of_birth=2015 + (n % 8),
                    enrolment_site=site,
                    enrolled_on=(now - timedelta(days=60 - n)).date(),
                    created_by=users["reader1"],
                )
                for day in (0, 7, 28):
                    collected = now - timedelta(days=60 - n - day, hours=n)
                    if collected > now:
                        continue
                    Sample.objects.create(
                        participant=participant,
                        sample_id=f"{participant.study_participant_id}-D{day:02d}",
                        visit=f"Day {day}",
                        collected_at=collected,
                        site=site,
                        created_by=users["reader1"],
                    )

        for project in Project.objects.filter(code__in=[p[0] for p in projects]):
            self.add_demo_results(project, users)
        self.add_demo_double_reading(Project.objects.get(code="MAL-2026-01"), users)

        self.stdout.write(self.style.SUCCESS(
            f"Demo data ready. Users: {', '.join(users)} (password is DEMO_PASSWORD in seed_demo.py)."
        ))
