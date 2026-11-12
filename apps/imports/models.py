from django.conf import settings
from django.core.validators import FileExtensionValidator
from django.db import models
from simple_history.models import HistoricalRecords

from apps.projects.models import Project
from apps.smears.models import SmearType, Slide

MAX_FILE_MB = 10


def validate_file_size(file):
    from django.core.exceptions import ValidationError

    if file.size > MAX_FILE_MB * 1024 * 1024:
        raise ValidationError(f"The file is larger than {MAX_FILE_MB} MB. Split it into smaller files.")


class ImportBatch(models.Model):
    """One uploaded file of existing results, from upload through to import."""

    class Status(models.TextChoices):
        UPLOADED = "uploaded", "Uploaded – columns not yet matched"
        CHECKED = "checked", "Checked – ready to import"
        IMPORTED = "imported", "Imported"
        CANCELLED = "cancelled", "Cancelled"

    class DateOrder(models.TextChoices):
        DMY = "dmy", "Day/month/year (15/09/2026)"
        MDY = "mdy", "Month/day/year (09/15/2026)"
        YMD = "ymd", "Year-month-day (2026-09-15)"

    class OnExisting(models.TextChoices):
        SKIP = "skip", "Skip it (useful when re-importing an updated file)"
        ERROR = "error", "Treat it as an error"

    project = models.ForeignKey(Project, on_delete=models.PROTECT, related_name="import_batches")
    smear_type = models.ForeignKey(SmearType, on_delete=models.PROTECT, related_name="+")
    file = models.FileField(
        upload_to="imports/%Y/%m/",
        validators=[FileExtensionValidator(["xlsx", "csv"]), validate_file_size],
        help_text=f"Excel (.xlsx) or CSV, up to {MAX_FILE_MB} MB. The first row must hold the column names.",
    )
    original_name = models.CharField(max_length=255)
    sheet_name = models.CharField(
        max_length=100, blank=True, help_text="Excel only. Leave blank to use the first sheet."
    )
    header_row = models.PositiveSmallIntegerField(
        default=1, help_text="The row number that holds the column names (usually 1)."
    )
    date_order = models.CharField(
        "Dates written as", max_length=3, choices=DateOrder.choices, default=DateOrder.DMY,
        help_text="Only matters for dates typed as text; real Excel dates are read correctly either way.",
    )
    on_existing_slide = models.CharField(
        "If a slide ID already exists", max_length=5, choices=OnExisting.choices, default=OnExisting.SKIP
    )

    mapping = models.JSONField(default=dict, blank=True, help_text="Target field → source column name.")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.UPLOADED)
    rows_total = models.PositiveIntegerField(default=0)
    rows_valid = models.PositiveIntegerField(default=0)
    rows_skipped = models.PositiveIntegerField(default=0)
    rows_imported = models.PositiveIntegerField(default=0)
    report = models.JSONField(
        default=dict, blank=True, help_text="Row errors, warnings and a preview, from the last check."
    )
    slides = models.ManyToManyField(Slide, blank=True, related_name="import_batches")

    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    imported_at = models.DateTimeField(null=True, blank=True)

    history = HistoricalRecords(excluded_fields=["report"])

    class Meta:
        ordering = ["-created_at"]
        verbose_name_plural = "import batches"

    def __str__(self):
        return f"Import #{self.pk} – {self.original_name}"
