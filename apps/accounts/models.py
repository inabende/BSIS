from django.contrib.auth.models import AbstractUser
from django.db import models
from simple_history.models import HistoricalRecords


class User(AbstractUser):
    """A staff member who uses the system.

    System admins are Django superusers. Project-level roles (lead, reader,
    reviewer, viewer) are held through ``projects.ProjectMembership``.
    """

    can_create_projects = models.BooleanField(
        default=False,
        help_text="Allows this user to create new projects. They become lead of projects they create.",
    )
    job_title = models.CharField(max_length=100, blank=True)

    history = HistoricalRecords()

    class Meta:
        ordering = ["first_name", "last_name", "username"]

    def __str__(self):
        return self.get_full_name() or self.username

    @property
    def is_system_admin(self):
        return self.is_active and self.is_superuser
