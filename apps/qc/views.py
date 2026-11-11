from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from django.views.generic import FormView, TemplateView, UpdateView, View
from simple_history.utils import update_change_reason

from apps.projects.mixins import ProjectAccessMixin
from apps.smears.models import Slide

from . import access
from .forms import QCSettingsForm, UnlockForm
from .models import FinalResult, qc_settings_for


def _slide_url(project, slide):
    return reverse("smears:slide_detail", args=[project.code, slide.pk])


def lock_final(final, user, note=""):
    final.locked = True
    final.locked_by = user
    final.locked_at = timezone.now()
    final.save()
    update_change_reason(final, note or "Approved and locked")


class ReviewQueueView(ProjectAccessMixin, TemplateView):
    """What still needs attention: second readings, tie-breakers, and results awaiting approval."""

    template_name = "qc/review_queue.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        slides = self.project.slides.select_related("sample__participant", "smear_type", "final_result")
        context["awaiting_second"] = slides.filter(status=Slide.Status.READING).order_by("created_at")
        context["awaiting_tiebreak"] = slides.filter(status=Slide.Status.DISCORDANT).order_by("created_at")
        context["awaiting_approval"] = slides.filter(
            final_result__isnull=False, final_result__locked=False
        ).order_by("final_result__had_discordance", "created_at")[:200]
        context["awaiting_approval_total"] = slides.filter(
            final_result__isnull=False, final_result__locked=False
        ).count()
        return context


class BulkApproveView(ProjectAccessMixin, View):
    """Approve and lock several final results at once from the review queue."""

    def post(self, request, *args, **kwargs):
        if not self.perms["can_review"]:
            raise PermissionDenied
        ids = [int(pk) for pk in request.POST.getlist("slide") if pk.isdigit()]
        finals = FinalResult.objects.filter(slide__project=self.project, slide_id__in=ids, locked=False)
        count = 0
        with transaction.atomic():
            for final in finals:
                lock_final(final, request.user)
                count += 1
        if count:
            messages.success(request, f"{count} result(s) approved and locked.")
        else:
            messages.warning(request, "No results were selected.")
        return redirect(reverse("qc:review", args=[self.project.code]))


class SlideActionMixin(ProjectAccessMixin):
    def get_slide(self):
        return get_object_or_404(Slide.objects.select_related("final_result"), pk=self.kwargs["pk"], project=self.project)


class LockView(SlideActionMixin, View):
    def post(self, request, *args, **kwargs):
        slide = self.get_slide()
        if not access.can_lock(request.user, slide):
            raise PermissionDenied
        lock_final(slide.final, request.user, request.POST.get("note", "").strip())
        messages.success(request, f"Final result for slide {slide} approved and locked.")
        return redirect(_slide_url(self.project, slide))


class UnlockView(SlideActionMixin, FormView):
    form_class = UnlockForm
    template_name = "qc/unlock.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["slide"] = self.slide
        return context

    def get(self, request, *args, **kwargs):
        self.slide = self._checked_slide()
        return super().get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        self.slide = self._checked_slide()
        return super().post(request, *args, **kwargs)

    def _checked_slide(self):
        slide = self.get_slide()
        if not access.can_unlock(self.request.user, slide):
            raise PermissionDenied
        return slide

    def form_valid(self, form):
        final = self.slide.final
        final.locked = False
        final.locked_by = None
        final.locked_at = None
        final.save()
        update_change_reason(final, f"Unlocked: {form.cleaned_data['reason']}")
        messages.success(self.request, f"Slide {self.slide} unlocked. Readings can now be corrected.")
        return redirect(_slide_url(self.project, self.slide))


class QCSettingsView(ProjectAccessMixin, UpdateView):
    required_permission = "manage"
    form_class = QCSettingsForm
    template_name = "qc/settings.html"

    def get_object(self):
        return qc_settings_for(self.project)

    def form_valid(self, form):
        messages.success(self.request, "Quality control settings saved. They apply to slides recorded from now on.")
        return super().form_valid(form)

    def get_success_url(self):
        return self.project.get_absolute_url()
