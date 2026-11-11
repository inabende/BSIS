from django.test import TestCase
from django.urls import reverse

from apps.projects.models import Project, ProjectMembership

from .factories import PASSWORD, add_member, make_admin, make_project, make_site, make_user

Role = ProjectMembership.Role


class ProjectViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.project = make_project("P1")
        cls.lead = make_user("lead", can_create_projects=True)
        cls.reader = make_user("reader")
        cls.outsider = make_user("outsider")
        add_member(cls.project, cls.lead, Role.LEAD)
        cls.reader_membership = add_member(cls.project, cls.reader, Role.READER)

    def login(self, user):
        self.client.login(username=user.username, password=PASSWORD)

    def test_login_required(self):
        response = self.client.get(reverse("projects:list"))
        self.assertRedirects(response, f"{reverse('login')}?next={reverse('projects:list')}")

    def test_non_member_gets_404(self):
        self.login(self.outsider)
        response = self.client.get(reverse("projects:detail", args=["P1"]))
        self.assertEqual(response.status_code, 404)

    def test_reader_can_view_but_not_edit(self):
        self.login(self.reader)
        self.assertEqual(self.client.get(reverse("projects:detail", args=["P1"])).status_code, 200)
        self.assertEqual(self.client.get(reverse("projects:update", args=["P1"])).status_code, 403)
        self.assertEqual(self.client.get(reverse("projects:member_add", args=["P1"])).status_code, 403)

    def test_create_project_makes_creator_lead(self):
        self.login(self.lead)
        site = make_site()
        response = self.client.post(
            reverse("projects:create"),
            {
                "code": "NEW-01",
                "name": "New study",
                "principal_investigator": "Dr X",
                "sites": [site.pk],
                "default_wbc_per_ul": 8000,
            },
        )
        project = Project.objects.get(code="NEW-01")
        self.assertRedirects(response, project.get_absolute_url())
        self.assertEqual(project.created_by, self.lead)
        self.assertTrue(project.memberships.filter(user=self.lead, role=Role.LEAD).exists())

    def test_reserved_code_rejected(self):
        self.login(self.lead)
        response = self.client.post(
            reverse("projects:create"),
            {"code": "new", "name": "X", "principal_investigator": "Y", "default_wbc_per_ul": 8000},
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Project.objects.filter(code="new").exists())

    def test_user_without_flag_cannot_create(self):
        self.login(self.reader)
        self.assertEqual(self.client.get(reverse("projects:create")).status_code, 403)

    def test_project_code_cannot_change(self):
        self.login(self.lead)
        self.client.post(
            reverse("projects:update", args=["P1"]),
            {"code": "CHANGED", "name": "Renamed", "principal_investigator": "Dr PI", "default_wbc_per_ul": 8000},
        )
        self.project.refresh_from_db()
        self.assertEqual(self.project.code, "P1")
        self.assertEqual(self.project.name, "Renamed")

    def test_lead_adds_member(self):
        self.login(self.lead)
        self.client.post(
            reverse("projects:member_add", args=["P1"]), {"user": self.outsider.pk, "role": Role.VIEWER}
        )
        self.assertTrue(self.project.memberships.filter(user=self.outsider, role=Role.VIEWER).exists())

    def test_cannot_remove_last_lead(self):
        self.login(self.lead)
        lead_membership = self.project.memberships.get(user=self.lead)
        self.client.post(reverse("projects:member_remove", args=["P1", lead_membership.pk]))
        self.assertTrue(self.project.memberships.filter(pk=lead_membership.pk).exists())

    def test_cannot_demote_last_lead(self):
        self.login(self.lead)
        lead_membership = self.project.memberships.get(user=self.lead)
        response = self.client.post(
            reverse("projects:member_role", args=["P1", lead_membership.pk]), {"role": Role.READER}
        )
        self.assertContains(response, "at least one lead")
        lead_membership.refresh_from_db()
        self.assertEqual(lead_membership.role, Role.LEAD)

    def test_lead_removes_reader(self):
        self.login(self.lead)
        self.client.post(reverse("projects:member_remove", args=["P1", self.reader_membership.pk]))
        self.assertFalse(self.project.memberships.filter(user=self.reader).exists())

    def test_close_project_records_reason(self):
        self.login(self.lead)
        self.client.post(reverse("projects:status", args=["P1"]), {"status": "closed", "reason": "Study ended"})
        self.project.refresh_from_db()
        self.assertEqual(self.project.status, "closed")
        self.assertEqual(self.project.history.first().history_change_reason, "Study ended")

    def test_lead_cannot_reopen_but_admin_can(self):
        self.project.status = Project.Status.CLOSED
        self.project.save()
        self.login(self.lead)
        self.assertEqual(self.client.get(reverse("projects:status", args=["P1"])).status_code, 403)
        self.login(make_admin())
        self.client.post(reverse("projects:status", args=["P1"]), {"status": "active", "reason": "Reopened"})
        self.project.refresh_from_db()
        self.assertEqual(self.project.status, "active")

    def test_history_page_shows_changes(self):
        self.login(self.lead)
        self.client.post(
            reverse("projects:update", args=["P1"]),
            {"name": "Renamed study", "principal_investigator": "Dr PI", "default_wbc_per_ul": 8000},
        )
        response = self.client.get(reverse("projects:history", args=["P1"]))
        self.assertContains(response, "Renamed study")
        self.assertContains(response, "lead")

    def test_dashboard_loads(self):
        self.login(self.reader)
        response = self.client.get(reverse("home"))
        self.assertContains(response, "P1")
