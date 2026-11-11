from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count
from django.views.generic import TemplateView

from apps.projects import permissions
from apps.projects.models import Project
from apps.samples.models import Participant, Sample


class HomeView(LoginRequiredMixin, TemplateView):
    """Dashboard: the user's projects and overall counts."""

    template_name = "core/home.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        projects = permissions.visible_projects(self.request.user)
        context["projects"] = (
            projects.filter(status=Project.Status.ACTIVE)
            .annotate(
                participant_count=Count("participants", distinct=True),
                sample_count=Count("samples", distinct=True),
            )
            .order_by("-created_at")[:12]
        )
        context["totals"] = {
            "projects": projects.count(),
            "participants": Participant.objects.filter(project__in=projects).count(),
            "samples": Sample.objects.filter(project__in=projects).count(),
        }
        context["recent_samples"] = (
            Sample.objects.filter(project__in=projects)
            .select_related("project", "participant")
            .order_by("-created_at")[:8]
        )
        context["can_create"] = permissions.can_create_project(self.request.user)
        from apps.projects.views import qc_counts
        from apps.smears.models import Slide

        context["qc"] = qc_counts(Slide.objects.filter(project__in=projects.filter(status=Project.Status.ACTIVE)))
        return context
