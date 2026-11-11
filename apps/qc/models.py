"""
Quality control: per-project rules for comparing readings, and the final
result each slide ends up with.
"""

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from simple_history.models import HistoricalRecords

from apps.projects.models import Project
from apps.smears.models import READING_SPECIES_CHOICES, Slide


class QCSettings(models.Model):
    """How a project compares double readings and settles disagreements."""

    class FinalRule(models.TextChoices):
        TIEBREAKER = "tiebreaker", "Tie-breaker's reading is the final result"
        CLOSEST_TWO = "closest_two", "Majority result; density = mean of the two closest readings"

    project = models.OneToOneField(Project, on_delete=models.CASCADE, related_name="qc_settings")
    density_threshold_pct = models.PositiveSmallIntegerField(
        "Density / parasitaemia discordance threshold (%)",
        default=50,
        validators=[MinValueValidator(1), MaxValueValidator(1000)],
        help_text="Readings disagree when the difference is more than this % of their mean. "
        "e.g. at 50%, 1,000 vs 1,800/µL disagree (57%); 1,000 vs 1,400/µL agree (33%).",
    )
    final_rule = models.CharField(
        "After a tie-breaker",
        max_length=15,
        choices=FinalRule.choices,
        default=FinalRule.TIEBREAKER,
    )

    history = HistoricalRecords()

    class Meta:
        verbose_name = "QC settings"
        verbose_name_plural = "QC settings"

    def __str__(self):
        return f"QC settings for {self.project.code}"


def qc_settings_for(project):
    obj, _ = QCSettings.objects.get_or_create(project=project)
    return obj


class FinalResult(models.Model):
    """The agreed result of a slide, worked out from its readings."""

    slide = models.OneToOneField(Slide, on_delete=models.CASCADE, related_name="final_result")
    is_positive = models.BooleanField(null=True, blank=True)
    species = models.CharField(max_length=15, choices=READING_SPECIES_CHOICES, blank=True)
    density_per_ul = models.DecimalField(
        "Parasite density (/µL)", max_digits=12, decimal_places=2, null=True, blank=True
    )
    parasitaemia_pct = models.DecimalField("Parasitaemia (%)", max_digits=8, decimal_places=4, null=True, blank=True)

    rule_applied = models.CharField(max_length=200, help_text="How this result was worked out.")
    readings_used = models.CharField(max_length=20, help_text="Reader numbers used, e.g. '1,2'.")
    had_discordance = models.BooleanField(default=False)
    discordance_reasons = models.JSONField(default=list, blank=True)
    decided_at = models.DateTimeField(auto_now=True)

    locked = models.BooleanField(default=False)
    locked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    locked_at = models.DateTimeField(null=True, blank=True)

    history = HistoricalRecords()

    class Meta:
        indexes = [models.Index(fields=["is_positive", "species"]), models.Index(fields=["locked"])]

    def __str__(self):
        return f"Final result for {self.slide}"

    @property
    def result_label(self):
        if self.is_positive is None:
            return ""
        return "Positive" if self.is_positive else "Negative"
