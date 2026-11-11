"""
Smear types, their configurable fields, and the slides and readings recorded against samples.

Design (see docs/02-architecture.md §4.1): values that are searched across
projects (positive/negative, species, density, parasitaemia) are real
columns on Reading; everything specific to one smear type is kept in
``Reading.values`` (JSON), validated against that type's FieldDefinitions.
"""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models
from django.utils import timezone
from simple_history.models import HistoricalRecords

from apps.projects.models import Project, Site
from apps.samples.models import Sample

SPECIES_CHOICES = [
    ("pf", "P. falciparum"),
    ("pv", "P. vivax"),
    ("pm", "P. malariae"),
    ("po", "P. ovale"),
    ("pk", "P. knowlesi"),
    ("unidentified", "Plasmodium sp. (unidentified)"),
]
MIXED = "mixed"
READING_SPECIES_CHOICES = SPECIES_CHOICES + [(MIXED, "Mixed infection")]


class SmearType(models.Model):
    """A kind of smear (e.g. malaria thick) and the rules for recording it."""

    class Calculation(models.TextChoices):
        NONE = "none", "None"
        THICK_DENSITY = "thick_density", "Malaria thick smear: parasite density"
        THIN_PARASITAEMIA = "thin_parasitaemia", "Malaria thin smear: parasitaemia %"
        HEMATOLOGY = "hematology_differential", "Hematology: differential must total 100%"

    code = models.CharField(
        max_length=40,
        unique=True,
        validators=[RegexValidator(r"^[a-z0-9_]+$", "Use lowercase letters, numbers and _ only.")],
    )
    name = models.CharField(max_length=100)
    slide_suffix = models.CharField(
        max_length=6,
        help_text="Added to the sample ID to suggest a slide ID, e.g. TK gives SM-001-TK.",
    )
    description = models.TextField(blank=True)
    calculation = models.CharField(
        max_length=30,
        choices=Calculation.choices,
        default=Calculation.NONE,
        help_text="Built-in calculations and checks applied when a reading is saved.",
    )
    is_builtin = models.BooleanField(default=False, editable=False)
    is_active = models.BooleanField(default=True)
    order = models.PositiveSmallIntegerField(default=100)

    history = HistoricalRecords()

    class Meta:
        ordering = ["order", "name"]

    def __str__(self):
        return self.name

    def active_fields(self):
        return self.fields.filter(is_active=True)


class FieldDefinition(models.Model):
    """One field shown on the result form for a smear type."""

    class DataType(models.TextChoices):
        INTEGER = "integer", "Whole number"
        DECIMAL = "decimal", "Decimal number"
        TEXT = "text", "Short text"
        LONGTEXT = "longtext", "Long text"
        CHOICE = "choice", "Pick one"
        MULTICHOICE = "multichoice", "Pick several"
        BOOLEAN = "boolean", "Yes / no"
        DATE = "date", "Date"

    CHOICE_TYPES = {DataType.CHOICE, DataType.MULTICHOICE}
    NUMBER_TYPES = {DataType.INTEGER, DataType.DECIMAL}

    smear_type = models.ForeignKey(SmearType, on_delete=models.CASCADE, related_name="fields")
    key = models.CharField(
        max_length=50,
        validators=[RegexValidator(r"^[a-z][a-z0-9_]*$", "Use lowercase letters, numbers and _, starting with a letter.")],
        help_text="Internal name, used in exports. Fields named 'result' (positive/negative) "
        "and 'species' are also used for cross-project search.",
    )
    label = models.CharField(max_length=100)
    data_type = models.CharField(max_length=12, choices=DataType.choices)
    choices = models.TextField(
        blank=True,
        help_text="For 'Pick one' / 'Pick several': one option per line, as 'value = Label' or just 'Label'.",
    )
    unit = models.CharField(max_length=20, blank=True)
    help_text = models.CharField(max_length=255, blank=True)
    required = models.BooleanField(default=False)
    required_if_positive = models.BooleanField(
        default=False, help_text="Required only when the 'result' field is Positive."
    )
    min_value = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    max_value = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    order = models.PositiveSmallIntegerField(default=100)
    is_builtin = models.BooleanField(default=False, editable=False)
    is_active = models.BooleanField(default=True)

    history = HistoricalRecords()

    class Meta:
        ordering = ["smear_type", "order", "id"]
        constraints = [
            models.UniqueConstraint(fields=["smear_type", "key"], name="unique_field_key_per_smear_type"),
        ]

    def __str__(self):
        return f"{self.smear_type.name}: {self.label}"

    def parsed_choices(self):
        """[(value, label), ...] from the one-per-line choices text."""
        options = []
        for line in self.choices.splitlines():
            line = line.strip()
            if not line:
                continue
            if "=" in line:
                value, label = (part.strip() for part in line.split("=", 1))
            else:
                label = line
                value = "_".join(line.lower().split())
            options.append((value, label))
        return options

    def clean(self):
        if self.pk and self.is_builtin:
            original = FieldDefinition.objects.get(pk=self.pk)
            if (original.key, original.data_type) != (self.key, self.data_type):
                raise ValidationError(
                    "The internal name and type of built-in fields can't change; calculations depend on them."
                )
        if self.data_type in self.CHOICE_TYPES and not self.parsed_choices():
            raise ValidationError({"choices": "Add at least one option for this field type."})
        if self.data_type not in self.NUMBER_TYPES and (self.min_value is not None or self.max_value is not None):
            raise ValidationError({"min_value": "Minimum and maximum only apply to number fields."})
        if self.min_value is not None and self.max_value is not None and self.min_value > self.max_value:
            raise ValidationError({"max_value": "Maximum must be greater than the minimum."})


class ProjectSmearType(models.Model):
    """Which smear types a project records."""

    class Readers(models.IntegerChoices):
        ONE = 1, "1 reader"
        TWO = 2, "2 independent readers (+ tie-breaker if they disagree)"

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="smear_type_links")
    smear_type = models.ForeignKey(SmearType, on_delete=models.PROTECT, related_name="project_links")
    readers_required = models.PositiveSmallIntegerField(choices=Readers.choices, default=Readers.ONE)

    history = HistoricalRecords()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["project", "smear_type"], name="unique_smear_type_per_project"),
        ]

    def __str__(self):
        return f"{self.project.code}: {self.smear_type}"


def allowed_smear_types(project):
    return SmearType.objects.filter(is_active=True, project_links__project=project)


def readers_required_for(project, smear_type):
    link = ProjectSmearType.objects.filter(project=project, smear_type=smear_type).first()
    return link.readers_required if link else 1


class Slide(models.Model):
    """A smear prepared from a sample."""

    class Status(models.TextChoices):
        PENDING = "pending", "Awaiting reading"
        READING = "reading", "Being read"
        DISCORDANT = "discordant", "Discordant – needs tie-breaker"
        FINAL = "final", "Final"

    class Stain(models.TextChoices):
        GIEMSA = "giemsa", "Giemsa"
        FIELD = "field", "Field's"
        WRIGHT = "wright", "Wright"
        WRIGHT_GIEMSA = "wright_giemsa", "Wright-Giemsa"
        LEISHMAN = "leishman", "Leishman"
        OTHER = "other", "Other"

    sample = models.ForeignKey(Sample, on_delete=models.PROTECT, related_name="slides")
    project = models.ForeignKey(Project, on_delete=models.PROTECT, related_name="slides", editable=False)
    smear_type = models.ForeignKey(SmearType, on_delete=models.PROTECT, related_name="slides")
    slide_id = models.CharField("Slide ID", max_length=60)
    stain = models.CharField(max_length=15, choices=Stain.choices, default=Stain.GIEMSA)
    prepared_on = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)
    readers_required = models.PositiveSmallIntegerField(
        default=1,
        editable=False,
        help_text="Copied from the project's setting when the slide is recorded, so later setting changes "
        "don't alter slides already in progress.",
    )
    notes = models.TextField(blank=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+", null=True, blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    history = HistoricalRecords()

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["project", "slide_id"], name="unique_slide_id_per_project"),
        ]

    def __str__(self):
        return self.slide_id

    def save(self, *args, **kwargs):
        self.project_id = self.sample.project_id
        super().save(*args, **kwargs)

    @property
    def final(self):
        """The slide's final result, or None while readings are still needed."""
        try:
            return self.final_result
        except models.ObjectDoesNotExist:
            return None

    @property
    def is_locked(self):
        final = self.final
        return bool(final and final.locked)


class Reading(models.Model):
    """One microscopist's reading of a slide."""

    slide = models.ForeignKey(Slide, on_delete=models.PROTECT, related_name="readings")
    reader_number = models.PositiveSmallIntegerField(
        default=1, help_text="1 = first reader, 2 = second reader, 3 = tie-breaker."
    )
    reader = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="readings")
    read_at = models.DateTimeField("Date and time read", default=timezone.now)
    site = models.ForeignKey(Site, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    microscope = models.CharField(max_length=50, blank=True)
    comments = models.TextField(blank=True)

    # Searchable values (filled in by the calculations, never typed directly).
    is_positive = models.BooleanField(null=True, blank=True)
    species = models.CharField(max_length=15, choices=READING_SPECIES_CHOICES, blank=True)
    density_per_ul = models.DecimalField(
        "Parasite density (/µL)", max_digits=12, decimal_places=2, null=True, blank=True
    )
    parasitaemia_pct = models.DecimalField(
        "Parasitaemia (%)", max_digits=8, decimal_places=4, null=True, blank=True
    )

    # Smear-type-specific values, keyed by FieldDefinition.key, plus calculated extras.
    values = models.JSONField(default=dict, blank=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+", null=True, blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    history = HistoricalRecords()

    class Meta:
        ordering = ["slide", "reader_number"]
        constraints = [
            models.UniqueConstraint(fields=["slide", "reader_number"], name="unique_reader_number_per_slide"),
        ]
        indexes = [
            models.Index(fields=["is_positive", "species"]),
        ]

    def __str__(self):
        return f"{self.slide} – reader {self.reader_number}"

    @property
    def result_label(self):
        if self.is_positive is None:
            return ""
        return "Positive" if self.is_positive else "Negative"
