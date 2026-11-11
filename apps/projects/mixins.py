from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.shortcuts import get_object_or_404

from . import permissions
from .models import Project


class ProjectAccessMixin(LoginRequiredMixin):
    """Loads ``self.project`` from the URL's ``code`` and checks access.

    Set ``required_permission`` to one of: "view", "manage",
    "change_status", "enter_data".
    """

    required_permission = "view"
    project_url_kwarg = "code"

    _checks = {
        "view": permissions.can_view_project,
        "manage": permissions.can_manage_project,
        "change_status": permissions.can_change_status,
        "enter_data": permissions.can_enter_data,
    }

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        self.project = get_object_or_404(Project, code=kwargs[self.project_url_kwarg])
        # Non-members get 404 so they can't tell which project codes exist.
        if not permissions.can_view_project(request.user, self.project):
            raise Http404
        if not self._checks[self.required_permission](request.user, self.project):
            raise PermissionDenied
        self.perms = permissions.project_permissions(request.user, self.project)
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["project"] = self.project
        context["perms_project"] = self.perms
        return context
