from django.contrib.auth.models import AnonymousUser
from django.test import TestCase

from apps.projects import permissions
from apps.projects.models import Project, ProjectMembership

from .factories import add_member, make_admin, make_project, make_user

Role = ProjectMembership.Role


class PermissionRulesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.project = make_project("P1")
        cls.other = make_project("P2")
        cls.admin = make_admin()
        cls.lead = make_user("lead")
        cls.reader = make_user("reader")
        cls.reviewer = make_user("reviewer")
        cls.viewer = make_user("viewer")
        cls.outsider = make_user("outsider")
        add_member(cls.project, cls.lead, Role.LEAD)
        add_member(cls.project, cls.reader, Role.READER)
        add_member(cls.project, cls.reviewer, Role.REVIEWER)
        add_member(cls.project, cls.viewer, Role.VIEWER)

    def test_users_see_only_their_projects(self):
        self.assertEqual(list(permissions.visible_projects(self.reader)), [self.project])
        self.assertEqual(permissions.visible_projects(self.outsider).count(), 0)
        self.assertEqual(permissions.visible_projects(AnonymousUser()).count(), 0)

    def test_admin_sees_everything(self):
        self.assertEqual(permissions.visible_projects(self.admin).count(), 2)
        self.assertTrue(permissions.can_manage_project(self.admin, self.other))

    def test_only_lead_manages(self):
        self.assertTrue(permissions.can_manage_project(self.lead, self.project))
        for user in (self.reader, self.reviewer, self.viewer, self.outsider):
            self.assertFalse(permissions.can_manage_project(user, self.project), user)

    def test_lead_and_reader_enter_data(self):
        self.assertTrue(permissions.can_enter_data(self.lead, self.project))
        self.assertTrue(permissions.can_enter_data(self.reader, self.project))
        for user in (self.reviewer, self.viewer, self.outsider):
            self.assertFalse(permissions.can_enter_data(user, self.project), user)

    def test_closed_project_is_read_only(self):
        self.project.status = Project.Status.CLOSED
        self.project.save()
        self.assertFalse(permissions.can_enter_data(self.reader, self.project))
        self.assertFalse(permissions.can_enter_data(self.admin, self.project))
        self.assertFalse(permissions.can_manage_project(self.lead, self.project))
        self.assertFalse(permissions.can_change_status(self.lead, self.project))
        self.assertTrue(permissions.can_change_status(self.admin, self.project))
        self.assertTrue(permissions.can_view_project(self.viewer, self.project))

    def test_project_creation_needs_flag(self):
        self.assertFalse(permissions.can_create_project(self.reader))
        self.assertTrue(permissions.can_create_project(make_user("creator", can_create_projects=True)))
        self.assertTrue(permissions.can_create_project(self.admin))

    def test_inactive_admin_has_no_admin_rights(self):
        self.admin.is_active = False
        self.assertFalse(self.admin.is_system_admin)
