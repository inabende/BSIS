from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.paginator import Paginator
from django.http import HttpResponse
from django.utils import timezone
from django.views.generic import TemplateView, View

from .exports import build_csv, build_xlsx, readings_for_export
from .filters import SearchForm
from .models import ExportLog
from .stats import dashboard_stats


class SearchView(LoginRequiredMixin, TemplateView):
    """Search final results across every project the user can see."""

    template_name = "reports/search.html"
    page_size = 50

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        searched = bool(self.request.GET)
        form = SearchForm(self.request.GET or None, user=self.request.user)
        context["form"] = form
        context["searched"] = searched
        if searched and not form.is_valid():
            context["slides"] = []
            return context
        slides = form.slides()
        page = Paginator(slides, self.page_size).get_page(self.request.GET.get("page"))
        context["page_obj"] = page
        context["is_paginated"] = page.has_other_pages()
        context["slides"] = page.object_list
        context["total"] = page.paginator.count
        context["active_filters"] = form.active_filters()
        return context


class ExportView(LoginRequiredMixin, View):
    """Download the current search as Excel or CSV. Every export is logged."""

    def get(self, request, fmt):
        form = SearchForm(request.GET or None, user=request.user)
        if request.GET and not form.is_valid():
            return HttpResponse("Invalid filters.", status=400)
        slides = list(form.slides())
        readings = readings_for_export(slides, request.user)
        filters = form.active_filters()
        stamp = timezone.localtime().strftime("%Y%m%d-%H%M")

        if fmt == "csv":
            response = HttpResponse(content_type="text/csv; charset=utf-8")
            response["Content-Disposition"] = f'attachment; filename="bsis-results-{stamp}.csv"'
            build_csv(response, slides)
            reading_count = 0
        else:
            response = HttpResponse(
                content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
            response["Content-Disposition"] = f'attachment; filename="bsis-results-{stamp}.xlsx"'
            build_xlsx(response, slides, readings, request.user, filters)
            reading_count = len(readings)

        ExportLog.objects.create(
            user=request.user,
            format=fmt,
            filters=filters,
            project_codes=sorted({s.project.code for s in slides}),
            slide_count=len(slides),
            reading_count=reading_count,
        )
        return response


class DashboardView(LoginRequiredMixin, TemplateView):
    """Summary statistics and charts across the user's projects."""

    template_name = "reports/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        form = SearchForm(self.request.GET or None, user=self.request.user)
        # The dashboard is about one smear type at a time, so counts aren't mixed
        # (a thick and a thin slide from the same sample would otherwise count twice).
        smear_types = form.fields["smear_type"].queryset
        form.fields["smear_type"].empty_label = "Default (malaria thick smear)"
        chosen = None
        if form.is_bound and form.is_valid():
            chosen = form.cleaned_data.get("smear_type")
        if chosen is None:
            chosen = smear_types.filter(code="malaria_thick").first() or smear_types.first()
        context["form"] = form
        context["smear_type"] = chosen
        context["active_filters"] = form.active_filters()
        if chosen is not None:
            slides = form.slides().filter(smear_type=chosen)
            context["stats"] = dashboard_stats(slides)
        return context
