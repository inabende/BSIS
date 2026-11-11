from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.projects.models import Project, ProjectMembership
from apps.projects.tests.factories import (
    PASSWORD,
    add_member,
    make_participant,
    make_project,
    make_sample,
    make_site,
    make_user,
)
from apps.samples.models import Participant, Sample

Role = ProjectMembership.Role


def when(hours_ago=2):
    return (timezone.localtime() - timedelta(hours=hours_ago)).strftime("%Y-%m-%dT%H:%M")


class ParticipantAndSampleTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.project = make_project("P1")
        cls.other_project = make_project("P2")
        cls.reader = make_user("reader")
        cls.viewer = make_user("viewer")
        add_member(cls.project, cls.reader, Role.READER)
        add_member(cls.project, cls.viewer, Role.VIEWER)
        add_member(cls.other_project, cls.reader, Role.READER)

    def setUp(self):
        self.client.login(username="reader", password=PASSWORD)

    def test_register_participant(self):
        response = self.client.post(
            reverse("samples:participant_create", args=["P1"]),
            {"study_participant_id": "PT-100", "sex": "F", "year_of_birth": 2018},
        )
        participant = Participant.objects.get(study_participant_id="PT-100")
        self.assertRedirects(response, reverse("samples:participant_detail", args=["P1", participant.pk]))
        self.assertEqual(participant.project, self.project)
        self.assertEqual(participant.created_by, self.reader)

    def test_duplicate_participant_id_rejected_in_same_project(self):
        make_participant(self.project, "PT-100")
        response = self.client.post(
            reverse("samples:participant_create", args=["P1"]), {"study_participant_id": "pt-100", "sex": "U"}
        )
        self.assertContains(response, "already exists")

    def test_same_participant_id_allowed_in_other_project(self):
        make_participant(self.project, "PT-100")
        self.client.post(
            reverse("samples:participant_create", args=["P2"]), {"study_participant_id": "PT-100", "sex": "U"}
        )
        self.assertEqual(Participant.objects.filter(study_participant_id="PT-100").count(), 2)

    def test_future_year_of_birth_rejected(self):
        response = self.client.post(
            reverse("samples:participant_create", args=["P1"]),
            {"study_participant_id": "PT-1", "sex": "U", "year_of_birth": timezone.now().year + 1},
        )
        self.assertContains(response, "Enter a year between")

    def test_add_sample(self):
        participant = make_participant(self.project)
        site = make_site()
        self.client.post(
            reverse("samples:sample_create", args=["P1", participant.pk]),
            {"sample_id": "SM-1", "visit": "Day 0", "collected_at": when(), "site": site.pk},
        )
        sample = Sample.objects.get(sample_id="SM-1")
        self.assertEqual(sample.project, self.project)
        self.assertEqual(sample.participant, participant)

    def test_future_collection_time_rejected(self):
        participant = make_participant(self.project)
        response = self.client.post(
            reverse("samples:sample_create", args=["P1", participant.pk]),
            {"sample_id": "SM-1", "collected_at": when(-5)},
        )
        self.assertContains(response, "can&#x27;t be in the future")

    def test_duplicate_sample_id_rejected(self):
        participant = make_participant(self.project)
        make_sample(participant, "SM-1")
        other = make_participant(self.project, "PT-002")
        response = self.client.post(
            reverse("samples:sample_create", args=["P1", other.pk]), {"sample_id": "SM-1", "collected_at": when()}
        )
        self.assertContains(response, "already exists")

    def test_viewer_cannot_add(self):
        participant = make_participant(self.project)
        self.client.login(username="viewer", password=PASSWORD)
        self.assertEqual(self.client.get(reverse("samples:participant_create", args=["P1"])).status_code, 403)
        self.assertEqual(
            self.client.get(reverse("samples:sample_create", args=["P1", participant.pk])).status_code, 403
        )
        self.assertEqual(
            self.client.get(reverse("samples:participant_detail", args=["P1", participant.pk])).status_code, 200
        )

    def test_participant_from_other_project_not_reachable(self):
        # A participant in P2 must not be reachable through P1's URLs.
        participant = make_participant(self.other_project)
        response = self.client.get(reverse("samples:participant_detail", args=["P1", participant.pk]))
        self.assertEqual(response.status_code, 404)

    def test_closed_project_blocks_data_entry(self):
        self.project.status = Project.Status.CLOSED
        self.project.save()
        self.assertEqual(self.client.get(reverse("samples:participant_create", args=["P1"])).status_code, 403)

    def test_edit_sample_keeps_id_and_records_history(self):
        participant = make_participant(self.project)
        sample = make_sample(participant, "SM-1")
        self.client.post(
            reverse("samples:sample_update", args=["P1", sample.pk]),
            {"sample_id": "HACKED", "visit": "Day 7", "collected_at": when()},
        )
        sample.refresh_from_db()
        self.assertEqual(sample.sample_id, "SM-1")
        self.assertEqual(sample.visit, "Day 7")
        response = self.client.get(reverse("samples:sample_history", args=["P1", sample.pk]))
        self.assertContains(response, "Day 7")

    def test_sample_search(self):
        participant = make_participant(self.project)
        make_sample(participant, "ALPHA-1")
        make_sample(participant, "BETA-1")
        response = self.client.get(reverse("samples:sample_list", args=["P1"]), {"q": "alpha"})
        self.assertContains(response, "ALPHA-1")
        self.assertNotContains(response, "BETA-1")
