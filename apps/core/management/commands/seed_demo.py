"""
Load demo data for development and training.

    python manage.py seed_demo

Creates sites, demo users, two projects, participants and samples.
FOR DEVELOPMENT ONLY. Never run this on the production server.

All demo users share the password in DEMO_PASSWORD below.
"""

from datetime import date, timedelta

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


class Command(BaseCommand):
    help = "Load demo data (development only)."

    def add_arguments(self, parser):
        parser.add_argument("--force", action="store_true", help="Run even when DEBUG is off.")

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

        self.stdout.write(self.style.SUCCESS(
            f"Demo data ready. Users: {', '.join(users)} (password is DEMO_PASSWORD in seed_demo.py)."
        ))
