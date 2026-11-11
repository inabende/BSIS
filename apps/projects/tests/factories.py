"""Small helpers for building test data."""

from django.utils import timezone

from apps.accounts.models import User
from apps.projects.models import Project, ProjectMembership, Site
from apps.samples.models import Participant, Sample

PASSWORD = "test-pass-12345"


def make_user(username, **extra):
    user = User.objects.create_user(username=username, password=PASSWORD, **extra)
    return user


def make_admin(username="admin"):
    return make_user(username, is_superuser=True, is_staff=True)


def make_site(code="S1", name="Site One"):
    return Site.objects.get_or_create(code=code, defaults={"name": name})[0]


def make_project(code="P1", **extra):
    defaults = {"name": f"Project {code}", "principal_investigator": "Dr PI"}
    defaults.update(extra)
    project = Project.objects.create(code=code, **defaults)
    project.sites.add(make_site())
    return project


def add_member(project, user, role):
    return ProjectMembership.objects.create(project=project, user=user, role=role)


def make_participant(project, pid="PT-001"):
    return Participant.objects.create(project=project, study_participant_id=pid)


def make_sample(participant, sid="SM-001"):
    return Sample.objects.create(
        participant=participant, sample_id=sid, collected_at=timezone.now() - timezone.timedelta(hours=1)
    )
