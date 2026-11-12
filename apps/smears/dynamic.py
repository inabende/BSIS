"""
Builds result-entry forms at runtime from a smear type's FieldDefinitions,
and turns saved values back into readable rows.

This is what lets admins add smear types and fields without code changes.
"""

import datetime
from decimal import Decimal

from django import forms

from apps.core.forms import BootstrapFormMixin, DateInput

from .models import FieldDefinition, READING_SPECIES_CHOICES

DT = FieldDefinition.DataType

# Calculated values stored alongside entered ones, with how to label them.
DERIVED_LABELS = {
    "density_reported": ("Density as recorded in the imported file", "/µL"),
    "parasitaemia_reported": ("Parasitaemia as recorded in the imported file", "%"),
    "original_reader": ("Reader named in the imported file", ""),
    "wbc_per_ul_used": ("WBC/µL used in calculation", "/µL"),
    "gametocyte_density_per_ul": ("Gametocyte density", "/µL"),
    "differential_total": ("Differential total", "%"),
}


def _form_field(definition):
    common = {
        "label": definition.label,
        "required": definition.required,
        "help_text": definition.help_text,
    }
    numeric_limits = {}
    if definition.min_value is not None:
        numeric_limits["min_value"] = definition.min_value
    if definition.max_value is not None:
        numeric_limits["max_value"] = definition.max_value

    if definition.data_type == DT.INTEGER:
        limits = {k: int(v) for k, v in numeric_limits.items()}
        return forms.IntegerField(**common, **limits)
    if definition.data_type == DT.DECIMAL:
        return forms.DecimalField(**common, **numeric_limits, max_digits=12, decimal_places=4)
    if definition.data_type == DT.TEXT:
        return forms.CharField(**common, max_length=255)
    if definition.data_type == DT.LONGTEXT:
        return forms.CharField(**common, widget=forms.Textarea(attrs={"rows": 2}))
    if definition.data_type == DT.CHOICE:
        choices = definition.parsed_choices()
        if len(choices) <= 3:
            return forms.ChoiceField(**common, choices=choices, widget=forms.RadioSelect)
        return forms.ChoiceField(**common, choices=[("", "---------")] + choices)
    if definition.data_type == DT.MULTICHOICE:
        return forms.MultipleChoiceField(
            **common, choices=definition.parsed_choices(), widget=forms.CheckboxSelectMultiple
        )
    if definition.data_type == DT.BOOLEAN:
        common["required"] = False  # an unticked box means "no"
        return forms.BooleanField(**common)
    if definition.data_type == DT.DATE:
        return forms.DateField(**common, widget=DateInput())
    raise ValueError(f"Unknown data type {definition.data_type}")


class SmearValuesForm(BootstrapFormMixin, forms.Form):
    """Base class; fields are added per smear type by ``build_values_form``."""

    definitions = ()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for definition in self.definitions:
            # Read by templates/core/_form.html.
            field = self.fields[definition.key]
            field.unit = definition.unit
            field.required_if_positive = definition.required_if_positive

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("result") == "positive":
            for definition in self.definitions:
                value = cleaned.get(definition.key)
                if definition.required_if_positive and value in (None, "", [], False):
                    self.add_error(definition.key, "Required for a positive slide.")
        return cleaned

    def to_json(self):
        """Cleaned data as JSON-safe values, leaving out blanks."""
        data = {}
        for definition in self.definitions:
            value = self.cleaned_data.get(definition.key)
            if value in (None, "", []):
                continue
            if definition.data_type == DT.BOOLEAN and value is False:
                data[definition.key] = False
                continue
            if isinstance(value, Decimal):
                value = float(value)
            elif isinstance(value, datetime.date):
                value = value.isoformat()
            data[definition.key] = value
        return data


def build_values_form(smear_type):
    """A Form class whose fields are the smear type's active field definitions."""
    definitions = list(smear_type.active_fields())
    attrs = {definition.key: _form_field(definition) for definition in definitions}
    attrs["definitions"] = definitions
    return type(f"{smear_type.code.title()}ValuesForm", (SmearValuesForm,), attrs)


def initial_from_values(values):
    """Saved JSON values → form initial data."""
    return dict(values or {})


def display_rows(reading):
    """[(label, display value, unit)] for every field that has a value, in field order."""
    values = reading.values or {}
    rows = []
    for definition in reading.slide.smear_type.fields.all():
        if definition.key not in values:
            continue
        value = values[definition.key]
        if definition.data_type in FieldDefinition.CHOICE_TYPES:
            labels = dict(definition.parsed_choices())
            if isinstance(value, list):
                value = ", ".join(labels.get(v, v) for v in value)
            else:
                value = labels.get(value, value)
        elif definition.data_type == DT.BOOLEAN:
            value = "Yes" if value else "No"
        rows.append((definition.label, value, definition.unit))
    for key, (label, unit) in DERIVED_LABELS.items():
        if key in values:
            rows.append((label, values[key], unit))
    return rows


SPECIES_LABELS = dict(READING_SPECIES_CHOICES)
