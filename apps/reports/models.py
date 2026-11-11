from django.conf import settings
from django.db import models


class ExportLog(models.Model):
    """A record of every data export: who took what, and when (data governance)."""

    class Format(models.TextChoices):
        XLSX = "xlsx", "Excel"
        CSV = "csv", "CSV"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="exports")
    created_at = models.DateTimeField(auto_now_add=True)
    format = models.CharField(max_length=4, choices=Format.choices)
    filters = models.JSONField(default=dict, blank=True, help_text="Search filters used for the export.")
    project_codes = models.JSONField(default=list, blank=True, help_text="Projects whose data was included.")
    slide_count = models.PositiveIntegerField()
    reading_count = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user} – {self.get_format_display()} export of {self.slide_count} slides on {self.created_at:%d %b %Y %H:%M}"
