from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from simple_history.models import HistoricalRecords

from apps.projects.models import Project, Site


class Participant(models.Model):
    """A study participant, identified only by their study ID (no personal identifiers)."""

    class Sex(models.TextChoices):
        FEMALE = "F", "Female"
        MALE = "M", "Male"
        UNKNOWN = "U", "Unknown / not recorded"

    project = models.ForeignKey(Project, on_delete=models.PROTECT, related_name="participants")
    study_participant_id = models.CharField("Participant ID", max_length=50)
    sex = models.CharField(max_length=1, choices=Sex.choices, default=Sex.UNKNOWN)
    year_of_birth = models.PositiveSmallIntegerField(null=True, blank=True)
    enrolment_site = models.ForeignKey(
        Site, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    enrolled_on = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+", null=True, blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    history = HistoricalRecords()

    class Meta:
        ordering = ["project", "study_participant_id"]
        constraints = [
            models.UniqueConstraint(
                fields=["project", "study_participant_id"], name="unique_participant_id_per_project"
            ),
        ]

    def __str__(self):
        return self.study_participant_id

    def clean(self):
        year = timezone.now().year
        if self.year_of_birth and not (1900 <= self.year_of_birth <= year):
            raise ValidationError({"year_of_birth": f"Enter a year between 1900 and {year}."})
        if self.enrolment_site_id and self.project_id and not self.project.sites.filter(
            pk=self.enrolment_site_id
        ).exists():
            raise ValidationError({"enrolment_site": "This site isn't part of the project."})


class Sample(models.Model):
    """A blood sample collected from a participant at a visit."""

    participant = models.ForeignKey(Participant, on_delete=models.PROTECT, related_name="samples")
    # Stored directly (as well as via participant) so sample IDs can be unique per project
    # and cross-project queries stay simple.
    project = models.ForeignKey(Project, on_delete=models.PROTECT, related_name="samples", editable=False)
    sample_id = models.CharField("Sample ID", max_length=50)
    visit = models.CharField(max_length=50, blank=True, help_text="e.g. Day 0, Day 7, Screening")
    collected_at = models.DateTimeField("Collection date and time")
    site = models.ForeignKey(Site, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    notes = models.TextField(blank=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+", null=True, blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    history = HistoricalRecords()

    class Meta:
        ordering = ["-collected_at"]
        constraints = [
            models.UniqueConstraint(fields=["project", "sample_id"], name="unique_sample_id_per_project"),
        ]

    def __str__(self):
        return self.sample_id

    def save(self, *args, **kwargs):
        self.project_id = self.participant.project_id
        super().save(*args, **kwargs)

    def clean(self):
        if self.collected_at and self.collected_at > timezone.now():
            raise ValidationError({"collected_at": "Collection time can't be in the future."})
