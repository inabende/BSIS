from decimal import Decimal

from django import forms
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.core.forms import BootstrapFormMixin, DateInput, DateTimeInput
from apps.projects.models import ProjectMembership

from .calculations import calculate
from .dynamic import build_values_form
from .models import Reading, Slide, allowed_smear_types

User = get_user_model()
Role = ProjectMembership.Role


class SlideForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Slide
        fields = ["smear_type", "slide_id", "stain", "prepared_on", "notes"]
        widgets = {
            "prepared_on": DateInput(),
            "notes": forms.Textarea(attrs={"rows": 2}),
        }
        help_texts = {"slide_id": "Leave blank to use the sample ID plus the smear type's suffix."}

    def __init__(self, *args, sample, **kwargs):
        super().__init__(*args, **kwargs)
        self.sample = sample
        self.instance.sample = sample
        self.instance.project = sample.project
        self.fields["slide_id"].required = False
        self.fields["smear_type"].empty_label = "— Choose smear type —"
        if self.instance.pk:
            # A slide's type and ID are fixed once recorded; its result fields depend on them.
            self.fields["smear_type"].disabled = True
            self.fields["slide_id"].disabled = True
            self.fields["smear_type"].queryset = type(self.instance.smear_type).objects.filter(
                pk=self.instance.smear_type_id
            )
        else:
            self.fields["smear_type"].queryset = allowed_smear_types(sample.project)

    def clean(self):
        cleaned = super().clean()
        smear_type = cleaned.get("smear_type")
        slide_id = (cleaned.get("slide_id") or "").strip()
        if not self.instance.pk and smear_type and not slide_id:
            slide_id = self._suggest_slide_id(smear_type)
        if slide_id:
            clash = Slide.objects.filter(project=self.sample.project, slide_id__iexact=slide_id)
            if self.instance.pk:
                clash = clash.exclude(pk=self.instance.pk)
            if clash.exists():
                self.add_error("slide_id", "A slide with this ID already exists in this project.")
            cleaned["slide_id"] = slide_id
            self.instance.slide_id = slide_id
        return cleaned

    def _suggest_slide_id(self, smear_type):
        base = f"{self.sample.sample_id}-{smear_type.slide_suffix}"
        candidate, n = base, 1
        while Slide.objects.filter(project=self.sample.project, slide_id__iexact=candidate).exists():
            n += 1
            candidate = f"{base}-{n}"
        return candidate


class ReadingForm(BootstrapFormMixin, forms.ModelForm):
    """Who read the slide, when and where — the parts common to every smear type."""

    class Meta:
        model = Reading
        fields = ["reader", "read_at", "site", "microscope", "comments"]
        widgets = {
            "read_at": DateTimeInput(),
            "comments": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, project, user, exclude_reader_ids=(), **kwargs):
        super().__init__(*args, **kwargs)
        # Readers who already read this slide can't read it again (independent readings).
        self.exclude_reader_ids = set(exclude_reader_ids)
        readers = User.objects.filter(
            is_active=True, memberships__project=project, memberships__role__in=[Role.LEAD, Role.READER]
        )
        if user.is_system_admin:
            readers = readers | User.objects.filter(pk=user.pk)
        if self.instance.pk:
            # Keep the original reader selectable even if they've since left the project.
            readers = readers | User.objects.filter(pk=self.instance.reader_id)
        self.fields["reader"].queryset = readers.exclude(pk__in=self.exclude_reader_ids).distinct()
        self.fields["reader"].label_from_instance = lambda u: f"{u} ({u.username})"
        self.fields["site"].queryset = project.sites.all()
        self.fields["site"].label = "Reading site"
        if not self.instance.pk and user.pk not in self.exclude_reader_ids:
            self.initial.setdefault("reader", user.pk)
            self.initial.setdefault("read_at", timezone.localtime().replace(second=0, microsecond=0))

    def clean_read_at(self):
        value = self.cleaned_data["read_at"]
        if value and value > timezone.now() + timezone.timedelta(minutes=5):
            raise ValidationError("Reading time can't be in the future.")
        return value


def values_form_for(smear_type, data=None, initial=None):
    return build_values_form(smear_type)(data=data, initial=initial, prefix="v")


def apply_calculations(values_form, smear_type, project):
    """Run calculations; on problems, attach the messages to the right fields. Returns results or None."""
    if not values_form.is_valid():
        return None
    try:
        return calculate(smear_type, values_form.to_json(), project)
    except ValidationError as error:
        for key, messages in error.message_dict.items():
            field = key if key in values_form.fields else None
            for message in messages:
                values_form.add_error(field, message)
        return None


@transaction.atomic
def save_reading(reading_form, values_form, results, slide, user, reader_number=1):
    reading = reading_form.save(commit=False)
    reading.slide = slide
    reading.reader_number = reader_number
    if not reading.pk:
        reading.created_by = user
    reading.values = {**values_form.to_json(), **_json_safe(results["derived"])}
    reading.is_positive = results["is_positive"]
    reading.species = results["species"]
    reading.density_per_ul = results["density_per_ul"]
    reading.parasitaemia_pct = results["parasitaemia_pct"]
    reading.save()
    from apps.qc.services import evaluate_slide

    evaluate_slide(slide)
    return reading


def other_reader_ids(slide, reading=None):
    """Users who read this slide, apart from `reading` itself."""
    qs = slide.readings.all()
    if reading is not None and reading.pk:
        qs = qs.exclude(pk=reading.pk)
    return list(qs.values_list("reader_id", flat=True))


def _json_safe(data):
    return {k: float(v) if isinstance(v, Decimal) else v for k, v in data.items()}
