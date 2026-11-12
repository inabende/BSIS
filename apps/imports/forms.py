import os

from django import forms

from apps.core.forms import BootstrapFormMixin
from apps.smears.models import allowed_smear_types

from . import parsing
from .engine import targets_for
from .models import ImportBatch


class UploadForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = ImportBatch
        fields = ["smear_type", "file", "sheet_name", "header_row", "date_order", "on_existing_slide"]
        widgets = {"on_existing_slide": forms.RadioSelect, "date_order": forms.RadioSelect}

    def __init__(self, *args, project, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["smear_type"].queryset = allowed_smear_types(project)
        self.fields["smear_type"].empty_label = "— What kind of smear are these results? —"
        self.fields["header_row"].widget.attrs["min"] = 1
        self.table = None

    def clean(self):
        cleaned = super().clean()
        upload = cleaned.get("file")
        if upload and not self.errors:
            try:
                self.table = parsing.read_table(
                    upload, upload.name, cleaned.get("sheet_name", ""), cleaned.get("header_row") or 1
                )
            except parsing.ParseError as error:
                raise forms.ValidationError(str(error))
            finally:
                upload.seek(0)
            if not self.table.rows:
                raise forms.ValidationError("The file has column names but no rows of data.")
        return cleaned

    def save(self, commit=True):
        self.instance.original_name = os.path.basename(self.cleaned_data["file"].name)
        return super().save(commit)


class MappingForm(forms.Form):
    """One drop-down per target field, listing the file's columns."""

    def __init__(self, *args, batch, columns, **kwargs):
        super().__init__(*args, **kwargs)
        self.targets = targets_for(batch.smear_type)
        choices = [("", "— not in this file —")] + [(c, c) for c in columns]
        for target in self.targets:
            self.fields[target.key] = forms.ChoiceField(
                choices=choices, required=False, label=target.label, help_text=target.help,
                initial=(batch.mapping or {}).get(target.key, ""),
                widget=forms.Select(attrs={"class": "form-select form-select-sm"}),
            )
            self.fields[target.key].target = target

    def groups(self):
        """Fields grouped for display: [(group name, [bound fields])]."""
        out = {}
        for target in self.targets:
            out.setdefault(target.group, []).append(self[target.key])
        return list(out.items())

    def clean(self):
        cleaned = super().clean()
        for target in self.targets:
            if target.required and not cleaned.get(target.key):
                self.add_error(target.key, "Choose the column that holds this.")
        used = {}
        for key, column in list(cleaned.items()):  # add_error() removes keys from cleaned_data
            if not column:
                continue
            if column in used:
                self.add_error(key, f"'{column}' is already used for {self.fields[used[column]].label}.")
            used.setdefault(column, key)
        return cleaned

    def mapping(self):
        return {k: v for k, v in self.cleaned_data.items() if v}
