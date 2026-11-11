from django import forms

from apps.core.forms import BootstrapFormMixin, DateInput, DateTimeInput

from .models import Participant, Sample


class ParticipantForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Participant
        fields = ["study_participant_id", "sex", "year_of_birth", "enrolment_site", "enrolled_on", "notes"]
        widgets = {
            "enrolled_on": DateInput(),
            "notes": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, project, **kwargs):
        super().__init__(*args, **kwargs)
        self.project = project
        self.instance.project = project
        self.fields["enrolment_site"].queryset = project.sites.all()
        if self.instance.pk:
            # Changing an ID after samples exist would break the link to source records.
            self.fields["study_participant_id"].disabled = True

    def clean_study_participant_id(self):
        value = self.cleaned_data["study_participant_id"].strip()
        clash = Participant.objects.filter(project=self.project, study_participant_id__iexact=value)
        if self.instance.pk:
            clash = clash.exclude(pk=self.instance.pk)
        if clash.exists():
            raise forms.ValidationError("A participant with this ID already exists in this project.")
        return value


class SampleForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Sample
        fields = ["sample_id", "visit", "collected_at", "site", "notes"]
        widgets = {
            "collected_at": DateTimeInput(),
            "notes": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, participant, **kwargs):
        super().__init__(*args, **kwargs)
        self.participant = participant
        self.instance.participant = participant
        self.instance.project = participant.project
        self.fields["site"].queryset = participant.project.sites.all()
        if not self.instance.pk and participant.enrolment_site_id:
            self.initial.setdefault("site", participant.enrolment_site_id)
        if self.instance.pk:
            self.fields["sample_id"].disabled = True

    def clean_sample_id(self):
        value = self.cleaned_data["sample_id"].strip()
        clash = Sample.objects.filter(project=self.participant.project, sample_id__iexact=value)
        if self.instance.pk:
            clash = clash.exclude(pk=self.instance.pk)
        if clash.exists():
            raise forms.ValidationError("A sample with this ID already exists in this project.")
        return value
