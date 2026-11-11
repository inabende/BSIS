from django.contrib import messages
from django.db.models import Prefetch, Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.functional import cached_property
from django.views.generic import DetailView, ListView, TemplateView, UpdateView, View

from apps.core.history import history_rows
from apps.projects.mixins import ProjectAccessMixin
from apps.samples.models import Sample

from .dynamic import SPECIES_LABELS, display_rows
from .forms import ReadingForm, SlideForm, apply_calculations, save_reading, values_form_for
from .models import READING_SPECIES_CHOICES, Reading, SmearType, Slide, allowed_smear_types


def slide_url(project, slide):
    return reverse("smears:slide_detail", args=[project.code, slide.pk])


class SmearRecordView(ProjectAccessMixin, View):
    """Record a new slide and its first reading for a sample, in one form."""

    required_permission = "enter_data"
    template_name = "smears/smear_record.html"

    @cached_property
    def sample(self):
        return get_object_or_404(
            Sample.objects.select_related("participant"), pk=self.kwargs["sample_pk"], project=self.project
        )

    def get(self, request, *args, **kwargs):
        initial = {}
        smear_type = self._chosen_type(request.GET.get("smear_type"))
        if smear_type:
            initial["smear_type"] = smear_type.pk
        slide_form = SlideForm(sample=self.sample, initial=initial)
        reading_form = ReadingForm(project=self.project, user=request.user, initial={"site": self.sample.site_id})
        values_form = values_form_for(smear_type) if smear_type else None
        return self.render(slide_form, reading_form, values_form, smear_type)

    def post(self, request, *args, **kwargs):
        slide_form = SlideForm(request.POST, sample=self.sample)
        reading_form = ReadingForm(request.POST, project=self.project, user=request.user)
        smear_type = self._chosen_type(request.POST.get("smear_type"))
        values_form = values_form_for(smear_type, data=request.POST) if smear_type else None

        slide_ok = slide_form.is_valid()
        reading_ok = reading_form.is_valid()
        results = apply_calculations(values_form, smear_type, self.project) if values_form else None

        if slide_ok and reading_ok and results is not None:
            slide = slide_form.save(commit=False)
            slide.created_by = request.user
            slide.save()
            save_reading(reading_form, values_form, results, slide, request.user)
            messages.success(request, f"{smear_type.name} result recorded on slide {slide}.")
            if "save_another" in request.POST:
                return redirect(reverse("smears:smear_record", args=[self.project.code, self.sample.pk]))
            return redirect(slide_url(self.project, slide))

        return self.render(slide_form, reading_form, values_form, smear_type)

    def _chosen_type(self, pk):
        if not pk or not str(pk).isdigit():
            return None
        return allowed_smear_types(self.project).filter(pk=pk).first()

    def render(self, slide_form, reading_form, values_form, smear_type):
        return render(
            self.request,
            self.template_name,
            {
                "project": self.project,
                "perms_project": self.perms,
                "sample": self.sample,
                "slide_form": slide_form,
                "reading_form": reading_form,
                "values_form": values_form,
                "smear_type": smear_type,
                "no_types": not allowed_smear_types(self.project).exists(),
            },
        )


class SmearFieldsView(ProjectAccessMixin, View):
    """HTMX: returns the result fields for the chosen smear type."""

    required_permission = "enter_data"

    def get(self, request, *args, **kwargs):
        pk = request.GET.get("smear_type")
        smear_type = allowed_smear_types(self.project).filter(pk=pk).first() if pk and pk.isdigit() else None
        return render(
            request,
            "smears/_values_fields.html",
            {"values_form": values_form_for(smear_type) if smear_type else None, "smear_type": smear_type},
        )


class SlideMixin(ProjectAccessMixin):
    def get_slide(self):
        return get_object_or_404(
            Slide.objects.select_related("sample__participant", "smear_type"),
            pk=self.kwargs["pk"],
            project=self.project,
        )


class SlideDetailView(SlideMixin, DetailView):
    template_name = "smears/slide_detail.html"
    context_object_name = "slide"

    def get_object(self):
        return self.get_slide()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        readings = self.object.readings.select_related("reader", "site")
        context["readings"] = [(r, display_rows(r)) for r in readings]
        return context


class SlideUpdateView(SlideMixin, UpdateView):
    required_permission = "enter_data"
    form_class = SlideForm
    template_name = "smears/slide_form.html"

    def get_object(self):
        return self.get_slide()

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["sample"] = self.object.sample
        return kwargs

    def form_valid(self, form):
        messages.success(self.request, "Slide details saved.")
        return super().form_valid(form)

    def get_success_url(self):
        return slide_url(self.project, self.object)


class ReadingUpdateView(SlideMixin, TemplateView):
    required_permission = "enter_data"
    template_name = "smears/reading_form.html"

    @cached_property
    def slide(self):
        return self.get_slide()

    @cached_property
    def reading(self):
        return get_object_or_404(Reading, pk=self.kwargs["reading_pk"], slide=self.slide)

    def get(self, request, *args, **kwargs):
        reading_form = ReadingForm(instance=self.reading, project=self.project, user=request.user)
        values_form = values_form_for(self.slide.smear_type, initial=self.reading.values)
        return self.render_forms(reading_form, values_form)

    def post(self, request, *args, **kwargs):
        reading_form = ReadingForm(request.POST, instance=self.reading, project=self.project, user=request.user)
        values_form = values_form_for(self.slide.smear_type, data=request.POST)
        reading_ok = reading_form.is_valid()
        results = apply_calculations(values_form, self.slide.smear_type, self.project)
        if reading_ok and results is not None:
            save_reading(reading_form, values_form, results, self.slide, request.user, self.reading.reader_number)
            messages.success(request, "Reading updated.")
            return redirect(slide_url(self.project, self.slide))
        return self.render_forms(reading_form, values_form)

    def render_forms(self, reading_form, values_form):
        return self.render_to_response(
            self.get_context_data(
                slide=self.slide,
                reading=self.reading,
                reading_form=reading_form,
                values_form=values_form,
                smear_type=self.slide.smear_type,
            )
        )


class SlideHistoryView(SlideMixin, DetailView):
    """History of the slide and all of its readings, newest first."""

    template_name = "core/history.html"

    def get_object(self):
        return self.get_slide()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        rows = [dict(row, record="Slide") for row in history_rows(self.object)]
        for reading in self.object.readings.all():
            rows += [dict(row, record=f"Reading (reader {reading.reader_number})") for row in history_rows(reading)]
        rows.sort(key=lambda row: row["date"], reverse=True)
        context["record_label"] = f"Slide {self.object}"
        context["back_url"] = slide_url(self.project, self.object)
        context["rows"] = rows
        return context


class ResultsListView(ProjectAccessMixin, ListView):
    """All slides in a project with their results, filterable."""

    template_name = "smears/results_list.html"
    context_object_name = "slides"
    paginate_by = 50

    def get_queryset(self):
        qs = (
            self.project.slides.select_related("sample__participant", "smear_type")
            .prefetch_related(Prefetch("readings", queryset=Reading.objects.select_related("reader")))
            .order_by("-created_at")
        )
        params = self.request.GET
        if params.get("smear_type", "").isdigit():
            qs = qs.filter(smear_type_id=params["smear_type"])
        if params.get("result") in ("positive", "negative"):
            qs = qs.filter(readings__reader_number=1, readings__is_positive=params["result"] == "positive")
        if params.get("species"):
            qs = qs.filter(readings__reader_number=1, readings__species=params["species"])
        query = params.get("q", "").strip()
        if query:
            qs = qs.filter(
                Q(slide_id__icontains=query)
                | Q(sample__sample_id__icontains=query)
                | Q(sample__participant__study_participant_id__icontains=query)
            )
        return qs.distinct()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["smear_types"] = SmearType.objects.filter(slides__project=self.project).distinct()
        context["species_choices"] = READING_SPECIES_CHOICES
        context["species_labels"] = SPECIES_LABELS
        return context
