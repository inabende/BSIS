import csv

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.http import FileResponse, HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils.functional import cached_property
from django.views.generic import ListView, TemplateView, View

from apps.projects.mixins import ProjectAccessMixin
from apps.smears.models import allowed_smear_types

from . import engine
from .forms import MappingForm, UploadForm
from .models import ImportBatch
from .templates_xlsx import build_template


class ImportMixin(ProjectAccessMixin):
    """Imports are for project leads (and system admins)."""

    required_permission = "manage"

    @cached_property
    def batch(self):
        return get_object_or_404(ImportBatch, pk=self.kwargs["pk"], project=self.project)

    def url(self, name, batch=None):
        return reverse(f"imports:{name}", args=[self.project.code, (batch or self.batch).pk])


class ImportListView(ImportMixin, ListView):
    template_name = "imports/import_list.html"
    context_object_name = "batches"
    paginate_by = 25

    def get_queryset(self):
        return self.project.import_batches.select_related("smear_type", "uploaded_by")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["smear_types"] = allowed_smear_types(self.project)
        return context


class ImportUploadView(ImportMixin, TemplateView):
    template_name = "imports/upload.html"

    def get(self, request, *args, **kwargs):
        return self.render_to_response(self.get_context_data(form=UploadForm(project=self.project)))

    def post(self, request, *args, **kwargs):
        form = UploadForm(request.POST, request.FILES, project=self.project)
        if not form.is_valid():
            return self.render_to_response(self.get_context_data(form=form))
        batch = form.save(commit=False)
        batch.project = self.project
        batch.uploaded_by = request.user
        batch.mapping = engine.auto_map(form.table.columns, engine.targets_for(batch.smear_type))
        batch.rows_total = len(form.table.rows)
        batch.save()
        messages.success(request, f"Uploaded {batch.original_name}: {batch.rows_total} rows. "
                                  "Check the column matches below.")
        return redirect(self.url("map", batch))


class ImportMapView(ImportMixin, TemplateView):
    template_name = "imports/map.html"

    def editable(self):
        if self.batch.status in (ImportBatch.Status.IMPORTED, ImportBatch.Status.CANCELLED):
            raise PermissionDenied
        return engine.load_table(self.batch)

    def get(self, request, *args, **kwargs):
        table = self.editable()
        form = MappingForm(batch=self.batch, columns=table.columns)
        return self.render_page(form, table)

    def post(self, request, *args, **kwargs):
        table = self.editable()
        form = MappingForm(request.POST, batch=self.batch, columns=table.columns)
        if not form.is_valid():
            return self.render_page(form, table)
        self.batch.mapping = form.mapping()
        self.batch.save(update_fields=["mapping"])
        engine.check(self.batch, request.user)
        return redirect(self.url("preview"))

    def render_page(self, form, table):
        sample_rows = [values for _, values in table.rows[:3]]
        examples = {c: [engine.parsing.as_text(r.get(c)) for r in sample_rows] for c in table.columns}
        unmapped = [c for c in table.columns if c not in (form.data.values() if form.is_bound else self.batch.mapping.values())]
        return self.render_to_response(self.get_context_data(
            batch=self.batch, form=form, examples=examples, columns=table.columns, unmapped=unmapped,
        ))


class ImportPreviewView(ImportMixin, TemplateView):
    template_name = "imports/preview.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        batch = self.batch
        report = batch.report or {}
        context.update(
            batch=batch,
            errors=report.get("errors", [])[:200],
            error_total=len(report.get("errors", [])),
            warnings=report.get("warnings", [])[:100],
            warning_total=len(report.get("warnings", [])),
            skipped=report.get("skipped", [])[:100],
            preview=report.get("preview", []),
            new_participants=report.get("new_participants", 0),
            imported_slides=batch.slides.select_related("smear_type", "final_result", "sample__participant")[:50]
            if batch.status == ImportBatch.Status.IMPORTED else [],
        )
        return context

    def post(self, request, *args, **kwargs):
        batch = self.batch
        if batch.status != ImportBatch.Status.CHECKED:
            raise PermissionDenied
        if batch.rows_total - batch.rows_valid - batch.rows_skipped > 0 and not request.POST.get("accept_errors"):
            messages.error(request, "Tick the box to confirm that rows with problems will be left out.")
            return redirect(self.url("preview"))
        count = engine.run_import(batch, request.user)
        messages.success(request, f"Imported {count} slide{'s' if count != 1 else ''} from {batch.original_name}.")
        return redirect(self.url("preview"))


class ImportCancelView(ImportMixin, View):
    def post(self, request, *args, **kwargs):
        if self.batch.status == ImportBatch.Status.IMPORTED:
            raise PermissionDenied
        self.batch.status = ImportBatch.Status.CANCELLED
        self.batch.save(update_fields=["status"])
        messages.info(request, "Import cancelled. Nothing was saved from this file.")
        return redirect(reverse("imports:list", args=[self.project.code]))


class ImportProblemsCSV(ImportMixin, View):
    """Every problem row, for fixing in the source file."""

    def get(self, request, *args, **kwargs):
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="import-{self.batch.pk}-problems.csv"'
        response.write("﻿")
        writer = csv.writer(response)
        writer.writerow(["Row in file", "Type", "Problem"])
        report = self.batch.report or {}
        for kind, items in (("Error", report.get("errors", [])), ("Warning", report.get("warnings", []))):
            for item in items:
                for message in item["messages"]:
                    writer.writerow([item["row"], kind, message])
        for item in report.get("skipped", []):
            writer.writerow([item["row"], "Skipped", item["message"]])
        return response


class ImportFileView(ImportMixin, View):
    """Download the original uploaded file (kept for audit)."""

    def get(self, request, *args, **kwargs):
        return FileResponse(self.batch.file.open("rb"), as_attachment=True, filename=self.batch.original_name)


class TemplateDownloadView(ImportMixin, View):
    """A blank spreadsheet with the right columns for a smear type, plus instructions."""

    def get(self, request, *args, **kwargs):
        smear_type = get_object_or_404(allowed_smear_types(self.project), pk=kwargs["smear_type_pk"])
        response = HttpResponse(content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        response["Content-Disposition"] = (
            f'attachment; filename="import-template-{self.project.code}-{smear_type.code}.xlsx"'
        )
        build_template(response, self.project, smear_type)
        return response
