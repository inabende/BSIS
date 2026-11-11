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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["sites"].queryset = Site.objects.filter(is_active=True)
        if self.instance.pk:
            # The code appears in URLs and sample labels, so it can't change once created.
            self.fields["code"].disabled = True


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
