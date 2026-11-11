from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, RegexValidator
from django.db import models
from simple_history.models import HistoricalRecords


# Codes that would clash with URLs such as /projects/new/.
RESERVED_CODES = {"new"}


class Site(models.Model):
    """A location where samples are collected or slides are read."""

    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=200)
    location = models.CharField(max_length=200, blank=True)
    is_active = models.BooleanField(default=True)

    history = HistoricalRecords()

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.code})"


class Project(models.Model):
    """A study whose blood smear results are recorded in the system."""

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        CLOSED = "closed", "Closed (read-only)"
        ARCHIVED = "archived", "Archived"

    code = models.CharField(
        max_length=30,
        unique=True,
        validators=[RegexValidator(r"^[A-Za-z0-9_-]+$", "Use letters, numbers, - and _ only.")],
        help_text="Short unique code, e.g. MAL-2026-01.",
    )
    name = models.CharField(max_length=255)
    protocol_id = models.CharField("Protocol / ethics ID", max_length=100, blank=True)
    principal_investigator = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    sites = models.ManyToManyField(Site, blank=True, related_name="projects")
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE)
    default_wbc_per_ul = models.PositiveIntegerField(
        "Default WBC/µL",
        default=8000,
        validators=[MinValueValidator(1)],
        help_text="Used to calculate thick smear parasite density when a measured WBC count isn't given.",
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+", null=True, blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    members = models.ManyToManyField(
        settings.AUTH_USER_MODEL, through="ProjectMembership", related_name="projects"
    )

    history = HistoricalRecords(m2m_fields=[sites])

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.code} – {self.name}"

    def get_absolute_url(self):
        from django.urls import reverse

        return reverse("projects:detail", kwargs={"code": self.code})

    def clean(self):
        if self.code and self.code.lower() in RESERVED_CODES:
            raise ValidationError({"code": "This code is reserved. Please choose another."})
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValidationError({"end_date": "End date can't be before the start date."})

    @property
    def is_read_only(self):
        return self.status != self.Status.ACTIVE


class ProjectMembership(models.Model):
    """A user's role within one project."""

    class Role(models.TextChoices):
        LEAD = "lead", "Project lead"
        READER = "reader", "Lab reader"
        REVIEWER = "reviewer", "Data reviewer"
        VIEWER = "viewer", "Viewer"

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="memberships")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="memberships"
    )
    role = models.CharField(max_length=10, choices=Role.choices)
    added_at = models.DateTimeField(auto_now_add=True)

    history = HistoricalRecords()

    class Meta:
        ordering = ["project", "role", "user__first_name"]
        constraints = [
            models.UniqueConstraint(fields=["project", "user"], name="unique_member_per_project"),
        ]

    def __str__(self):
        return f"{self.user} – {self.get_role_display()} on {self.project.code}"
