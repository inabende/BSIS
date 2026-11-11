"""
The search form shared by cross-project search, exports and the reports dashboard.

Every query starts from the projects the user can see (permissions.visible_projects),
and only ever filters on *final* results, so blinded readings never leak.
"""

from django import forms
from django.db.models import Q

from apps.core.forms import BootstrapFormMixin, DateInput
from apps.projects import permissions
from apps.projects.models import Site
from apps.smears.models import READING_SPECIES_CHOICES, SmearType, Slide

STATUS_CHOICES = [
    ("", "Any status"),
    ("reading", "Awaiting reader 2"),
    ("discordant", "Awaiting tie-breaker"),
    ("final", "Final, not yet approved"),
    ("locked", "Approved and locked"),
    ("complete", "Has a final result (approved or not)"),
]


class SearchForm(BootstrapFormMixin, forms.Form):
    q = forms.CharField(label="Slide, sample or participant ID", required=False)
    project = forms.ModelMultipleChoiceField(queryset=None, required=False, label="Projects")
    smear_type = forms.ModelChoiceField(queryset=SmearType.objects.all(), required=False, empty_label="All smear types")
    result = forms.ChoiceField(
        choices=[("", "Any result"), ("positive", "Positive"), ("negative", "Negative")], required=False
    )
    species = forms.ChoiceField(choices=[("", "Any species")] + READING_SPECIES_CHOICES, required=False)
    status = forms.ChoiceField(choices=STATUS_CHOICES, required=False)
    site = forms.ModelChoiceField(queryset=Site.objects.all(), required=False, empty_label="All sites")
    collected_from = forms.DateField(required=False, label="Collected from", widget=DateInput())
    collected_to = forms.DateField(required=False, label="Collected to", widget=DateInput())
    density_min = forms.DecimalField(required=False, min_value=0, label="Density from (/µL)")
    density_max = forms.DecimalField(required=False, min_value=0, label="Density to (/µL)")

    def __init__(self, data=None, *, user, **kwargs):
        super().__init__(data, **kwargs)
        self.user = user
        self.projects = permissions.visible_projects(user).order_by("code")
        self.fields["project"].queryset = self.projects
        self.fields["project"].label_from_instance = lambda p: f"{p.code} – {p.name}"
        self.fields["project"].widget.attrs["size"] = min(6, max(2, self.projects.count()))
        self.fields["smear_type"].queryset = SmearType.objects.filter(slides__project__in=self.projects).distinct()
        self.fields["site"].queryset = Site.objects.filter(projects__in=self.projects).distinct()

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("collected_from") and cleaned.get("collected_to") and cleaned["collected_from"] > cleaned["collected_to"]:
            self.add_error("collected_to", "Must be on or after the 'from' date.")
        if cleaned.get("density_min") is not None and cleaned.get("density_max") is not None \
                and cleaned["density_min"] > cleaned["density_max"]:
            self.add_error("density_max", "Must be at least the 'from' density.")
        return cleaned

    def slides(self):
        """Slides matching the filters, limited to the user's projects. Call after is_valid()."""
        qs = Slide.objects.filter(project__in=self.projects).select_related(
            "project", "sample__participant", "sample__site", "smear_type", "final_result__locked_by"
        )
        data = self.cleaned_data if self.is_bound and self.is_valid() else {}
        return apply_filters(qs, data).order_by("project__code", "-sample__collected_at", "slide_id")

    def active_filters(self):
        """{label: display value} of filters in use, for export metadata and page headings."""
        if not (self.is_bound and self.is_valid()):
            return {}
        shown = {}
        for name, value in self.cleaned_data.items():
            if value in (None, "", []) or (hasattr(value, "exists") and not value.exists()):
                continue
            field = self.fields[name]
            if hasattr(value, "__iter__") and not isinstance(value, str):
                display = ", ".join(str(getattr(v, "code", v)) for v in value)
            elif getattr(field, "choices", None) and not hasattr(value, "pk"):
                display = dict(field.choices).get(value, value)
            else:
                display = str(value)
            label = field.label or name.replace("_", " ").capitalize()
            shown[str(label)] = display
        return shown


def apply_filters(qs, data):
    if data.get("project"):
        qs = qs.filter(project__in=data["project"])
    if data.get("smear_type"):
        qs = qs.filter(smear_type=data["smear_type"])
    if data.get("result") in ("positive", "negative"):
        qs = qs.filter(final_result__is_positive=data["result"] == "positive")
    if data.get("species"):
        qs = qs.filter(final_result__species=data["species"])
    status = data.get("status")
    if status in ("reading", "discordant"):
        qs = qs.filter(status=status)
    elif status == "final":
        qs = qs.filter(final_result__isnull=False, final_result__locked=False)
    elif status == "locked":
        qs = qs.filter(final_result__locked=True)
    elif status == "complete":
        qs = qs.filter(final_result__isnull=False)
    if data.get("site"):
        qs = qs.filter(sample__site=data["site"])
    if data.get("collected_from"):
        qs = qs.filter(sample__collected_at__date__gte=data["collected_from"])
    if data.get("collected_to"):
        qs = qs.filter(sample__collected_at__date__lte=data["collected_to"])
    if data.get("density_min") is not None:
        qs = qs.filter(final_result__density_per_ul__gte=data["density_min"])
    if data.get("density_max") is not None:
        qs = qs.filter(final_result__density_per_ul__lte=data["density_max"])
    query = (data.get("q") or "").strip()
    if query:
        qs = qs.filter(
            Q(slide_id__icontains=query)
            | Q(sample__sample_id__icontains=query)
            | Q(sample__participant__study_participant_id__icontains=query)
        )
    return qs
