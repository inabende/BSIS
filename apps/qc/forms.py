from django import forms

from apps.core.forms import BootstrapFormMixin
from apps.smears.models import ProjectSmearType

from .models import QCSettings


class QCSettingsForm(BootstrapFormMixin, forms.ModelForm):
    """Project-level thresholds, plus one 'readers required' field per smear type the project uses."""

    class Meta:
        model = QCSettings
        fields = ["density_threshold_pct", "final_rule"]
        widgets = {"final_rule": forms.RadioSelect}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.links = list(self.instance.project.smear_type_links.select_related("smear_type"))
        for link in self.links:
            self.fields[self.field_name(link)] = forms.TypedChoiceField(
                label=f"{link.smear_type.name}: readers required",
                choices=ProjectSmearType.Readers.choices,
                coerce=int,
                initial=link.readers_required,
            )
        # Readers fields first, then the thresholds.
        order = [self.field_name(link) for link in self.links] + ["density_threshold_pct", "final_rule"]
        self.order_fields(order)
        # BootstrapFormMixin ran before the dynamic fields were added.
        for link in self.links:
            self.fields[self.field_name(link)].widget.attrs["class"] = "form-select"

    @staticmethod
    def field_name(link):
        return f"readers_{link.smear_type_id}"

    def save(self, commit=True):
        settings = super().save(commit)
        for link in self.links:
            value = self.cleaned_data[self.field_name(link)]
            if link.readers_required != value:
                link.readers_required = value
                link.save(update_fields=["readers_required"])
        return settings


class UnlockForm(BootstrapFormMixin, forms.Form):
    reason = forms.CharField(
        max_length=255,
        widget=forms.Textarea(attrs={"rows": 2}),
        help_text="Recorded in the slide's history. e.g. 'Transcription error in reader 2 density found during monitoring.'",
    )
