from django import forms
from django.contrib.auth import get_user_model

from apps.core.forms import BootstrapFormMixin, DateInput

from .models import Project, ProjectMembership, Site

User = get_user_model()


class ProjectForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Project
        fields = [
            "code",
            "name",
            "protocol_id",
            "principal_investigator",
            "description",
            "sites",
            "start_date",
            "end_date",
            "default_wbc_per_ul",
        ]
        widgets = {
            "start_date": DateInput(),
            "end_date": DateInput(),
            "description": forms.Textarea(attrs={"rows": 3}),
            "sites": forms.CheckboxSelectMultiple(),
        }

    smear_types = forms.ModelMultipleChoiceField(
        queryset=None,
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label="Smear types recorded in this project",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from apps.smears.models import SmearType

        self.fields["sites"].queryset = Site.objects.filter(is_active=True)
        self.fields["smear_types"].queryset = SmearType.objects.filter(is_active=True)
        if self.instance.pk:
            # The code appears in URLs and sample labels, so it can't change once created.
            self.fields["code"].disabled = True
            self.initial["smear_types"] = list(
                self.instance.smear_type_links.values_list("smear_type_id", flat=True)
            )
        else:
            self.initial["smear_types"] = list(
                SmearType.objects.filter(is_active=True, is_builtin=True).values_list("pk", flat=True)
            )

    def save(self, commit=True):
        project = super().save(commit)
        if commit:
            self.save_smear_types()
        return project

    def save_smear_types(self):
        from apps.smears.models import ProjectSmearType

        chosen = set(self.cleaned_data.get("smear_types") or [])
        links = self.instance.smear_type_links.select_related("smear_type")
        for link in links:
            # Only unlink active types shown on the form; inactive ones stay as they were.
            if link.smear_type.is_active and link.smear_type not in chosen:
                link.delete()
        existing = {link.smear_type_id for link in self.instance.smear_type_links.all()}
        for smear_type in chosen:
            if smear_type.pk not in existing:
                ProjectSmearType.objects.create(project=self.instance, smear_type=smear_type)


class ProjectStatusForm(BootstrapFormMixin, forms.Form):
    status = forms.ChoiceField(choices=Project.Status.choices)
    reason = forms.CharField(max_length=255, help_text="Why is the status changing?")


class MembershipForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = ProjectMembership
        fields = ["user", "role"]

    def __init__(self, *args, project, **kwargs):
        super().__init__(*args, **kwargs)
        self.project = project
        existing = project.memberships.values_list("user_id", flat=True)
        self.fields["user"].queryset = User.objects.filter(is_active=True).exclude(pk__in=existing)
        self.fields["user"].label_from_instance = lambda u: f"{u} ({u.username})"

    def save(self, commit=True):
        self.instance.project = self.project
        return super().save(commit)


class MembershipRoleForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = ProjectMembership
        fields = ["role"]
