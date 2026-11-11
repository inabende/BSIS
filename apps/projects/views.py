from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect
from django.views.generic import CreateView, DetailView, FormView, ListView, UpdateView, View
from simple_history.utils import update_change_reason

from apps.core.history import history_rows

from . import permissions
from .forms import MembershipForm, MembershipRoleForm, ProjectForm, ProjectStatusForm
from .mixins import ProjectAccessMixin
from .models import Project, ProjectMembership

Role = ProjectMembership.Role


class ProjectListView(LoginRequiredMixin, ListView):
    template_name = "projects/project_list.html"
    context_object_name = "projects"
    paginate_by = 25

    def get_queryset(self):
        qs = permissions.visible_projects(self.request.user).annotate(
            participant_count=Count("participants", distinct=True),
            sample_count=Count("samples", distinct=True),
        )
        status = self.request.GET.get("status")
        if status in Project.Status.values:
            qs = qs.filter(status=status)
        query = self.request.GET.get("q", "").strip()
        if query:
            qs = qs.filter(Q(name__icontains=query) | Q(code__icontains=query))
        return qs.order_by("-created_at")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["can_create"] = permissions.can_create_project(self.request.user)
        context["statuses"] = Project.Status.choices
        return context


class ProjectCreateView(LoginRequiredMixin, CreateView):
    model = Project
    form_class = ProjectForm
    template_name = "projects/project_form.html"

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and not permissions.can_create_project(request.user):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)

    @transaction.atomic
    def form_valid(self, form):
        form.instance.created_by = self.request.user
        response = super().form_valid(form)
        # The creator becomes the project's lead.
        ProjectMembership.objects.create(project=self.object, user=self.request.user, role=Role.LEAD)
        messages.success(self.request, f"Project {self.object.code} created. You are its lead.")
        return response

    def get_success_url(self):
        return self.object.get_absolute_url()


class ProjectDetailView(ProjectAccessMixin, DetailView):
    template_name = "projects/project_detail.html"
    context_object_name = "project"

    def get_object(self):
        return self.project

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["memberships"] = self.project.memberships.select_related("user")
        context["participant_count"] = self.project.participants.count()
        context["sample_count"] = self.project.samples.count()
        context["slide_count"] = self.project.slides.count()
        context["smear_types"] = [link.smear_type for link in self.project.smear_type_links.select_related("smear_type")]
        context["recent_samples"] = self.project.samples.select_related("participant", "site")[:10]
        return context


class ProjectUpdateView(ProjectAccessMixin, UpdateView):
    required_permission = "manage"
    form_class = ProjectForm
    template_name = "projects/project_form.html"

    def get_object(self):
        return self.project

    def form_valid(self, form):
        messages.success(self.request, "Project details saved.")
        return super().form_valid(form)

    def get_success_url(self):
        return self.project.get_absolute_url()


class ProjectStatusView(ProjectAccessMixin, FormView):
    required_permission = "change_status"
    form_class = ProjectStatusForm
    template_name = "projects/project_status.html"

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        if not self.request.user.is_system_admin:
            # Only system admins can reopen a closed project.
            form.fields["status"].choices = [
                c for c in Project.Status.choices if c[0] != Project.Status.ACTIVE
            ]
        return form

    def get_initial(self):
        return {"status": self.project.status}

    def form_valid(self, form):
        self.project.status = form.cleaned_data["status"]
        self.project.save()
        update_change_reason(self.project, form.cleaned_data["reason"])
        messages.success(self.request, f"Status changed to {self.project.get_status_display()}.")
        return redirect(self.project.get_absolute_url())


class ProjectHistoryView(ProjectAccessMixin, DetailView):
    template_name = "core/history.html"

    def get_object(self):
        return self.project

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["record_label"] = f"Project {self.project.code}"
        context["back_url"] = self.project.get_absolute_url()
        context["rows"] = history_rows(self.project)
        return context


# --- Members ----------------------------------------------------------------


def _would_leave_no_lead(membership, new_role=None):
    """True if changing/removing this membership leaves the project without a lead."""
    if membership.role != Role.LEAD or new_role == Role.LEAD:
        return False
    return not membership.project.memberships.filter(role=Role.LEAD).exclude(pk=membership.pk).exists()


class MemberAddView(ProjectAccessMixin, CreateView):
    required_permission = "manage"
    form_class = MembershipForm
    template_name = "projects/member_form.html"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["project"] = self.project
        return kwargs

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(
            self.request, f"{self.object.user} added as {self.object.get_role_display().lower()}."
        )
        return response

    def get_success_url(self):
        return self.project.get_absolute_url() + "#members"


class MemberRoleView(ProjectAccessMixin, UpdateView):
    required_permission = "manage"
    form_class = MembershipRoleForm
    template_name = "projects/member_form.html"

    def get_object(self):
        return get_object_or_404(ProjectMembership, pk=self.kwargs["pk"], project=self.project)

    def form_valid(self, form):
        if _would_leave_no_lead(ProjectMembership.objects.get(pk=self.object.pk), form.cleaned_data["role"]):
            form.add_error("role", "A project must keep at least one lead.")
            return self.form_invalid(form)
        messages.success(self.request, f"{self.object.user}'s role updated.")
        return super().form_valid(form)

    def get_success_url(self):
        return self.project.get_absolute_url() + "#members"


class MemberRemoveView(ProjectAccessMixin, View):
    required_permission = "manage"

    def post(self, request, *args, **kwargs):
        membership = get_object_or_404(ProjectMembership, pk=kwargs["pk"], project=self.project)
        if _would_leave_no_lead(membership):
            messages.error(request, "You can't remove the last lead. Add another lead first.")
        else:
            membership.delete()
            messages.success(request, f"{membership.user} removed from the project.")
        return redirect(self.project.get_absolute_url() + "#members")
