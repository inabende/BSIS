from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db.models import Prefetch, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.functional import cached_property
from django.views.generic import DetailView, ListView, TemplateView, UpdateView, View

from apps.core.history import history_rows
from apps.projects import permissions
from apps.projects.mixins import ProjectAccessMixin
from apps.qc import access
from apps.qc.services import discordance_for
from apps.samples.models import Sample

from .dynamic import display_rows
from .forms import (
    ReadingForm,
    SlideForm,
    apply_calculations,
    other_reader_ids,
    save_reading,
    values_form_for,
)
from .models import READING_SPECIES_CHOICES, Reading, SmearType, Slide, allowed_smear_types, readers_required_for


def slide_url(project, slide):
    return reverse("smears:slide_detail", args=[project.code, slide.pk])


def saved_message(slide):
    """What to tell the user after a reading is saved, based on where the slide now stands."""
    if slide.status == Slide.Status.READING:
        return f"Saved. Slide {slide} needs a second independent reading before it has a final result."
    if slide.status == Slide.Status.DISCORDANT:
        return f"Saved. The two readings of slide {slide} disagree, so it needs a tie-breaker reading."
    return f"Saved. Slide {slide} has a final result."


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
            slide.readers_required = readers_required_for(self.project, smear_type)
            slide.save()
            save_reading(reading_form, values_form, results, slide, request.user)
            messages.success(request, saved_message(slide))
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
                "double_read_types": [
                    link.smear_type.name
                    for link in self.project.smear_type_links.filter(readers_required=2).select_related("smear_type")
                ],
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
            Slide.objects.select_related("sample__participant", "smear_type", "final_result__locked_by"),
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
        slide, user = self.object, self.request.user
        readings = []
        for reading in slide.readings.select_related("reader", "site"):
            visible = access.can_see_reading(user, slide, reading)
            readings.append(
                {
                    "reading": reading,
                    "visible": visible,
                    "rows": display_rows(reading) if visible else [],
                    "can_edit": access.can_edit_reading(user, slide, reading),
                }
            )
        context["readings"] = readings
        context["final"] = slide.final
        context["next_reader"] = access.next_reader_number(slide)
        context["can_add_reading"] = access.can_add_reading(user, slide)
        context["can_edit_slide"] = access.can_edit_slide(user, slide)
        context["can_lock"] = access.can_lock(user, slide)
        context["can_unlock"] = access.can_unlock(user, slide)
        sees_all = permissions.sees_blinded_results(user, self.project)
        context["sees_blinded"] = sees_all
        if slide.status == Slide.Status.DISCORDANT and sees_all:
            context["current_discordance"] = discordance_for(slide)
        return context


class SlideUpdateView(SlideMixin, UpdateView):
    required_permission = "enter_data"
    form_class = SlideForm
    template_name = "smears/slide_form.html"

    def get_object(self):
        slide = self.get_slide()
        if not access.can_edit_slide(self.request.user, slide):
            raise PermissionDenied
        return slide

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["sample"] = self.object.sample
        return kwargs

    def form_valid(self, form):
        messages.success(self.request, "Slide details saved.")
        return super().form_valid(form)

    def get_success_url(self):
        return slide_url(self.project, self.object)


class ReadingFormMixin(SlideMixin):
    template_name = "smears/reading_form.html"
    required_permission = "enter_data"

    @cached_property
    def slide(self):
        return self.get_slide()

    def render_forms(self, reading_form, values_form, **extra):
        return self.render_to_response(
            self.get_context_data(
                slide=self.slide,
                reading_form=reading_form,
                values_form=values_form,
                smear_type=self.slide.smear_type,
                **extra,
            )
        )


class ReadingCreateView(ReadingFormMixin, TemplateView):
    """Add reader 2's reading, or the tie-breaker (reader 3), to an existing slide."""

    def check(self):
        if not access.can_add_reading(self.request.user, self.slide):
            raise PermissionDenied
        return access.next_reader_number(self.slide)

    def forms(self, data=None):
        exclude = other_reader_ids(self.slide)
        reading_form = ReadingForm(
            data, project=self.project, user=self.request.user, exclude_reader_ids=exclude,
            initial={"site": self.slide.sample.site_id},
        )
        return reading_form, values_form_for(self.slide.smear_type, data=data)

    def get(self, request, *args, **kwargs):
        number = self.check()
        reading_form, values_form = self.forms()
        return self.render_forms(reading_form, values_form, reader_number=number)

    def post(self, request, *args, **kwargs):
        number = self.check()
        reading_form, values_form = self.forms(request.POST)
        reading_ok = reading_form.is_valid()
        results = apply_calculations(values_form, self.slide.smear_type, self.project)
        if reading_ok and results is not None:
            save_reading(reading_form, values_form, results, self.slide, request.user, reader_number=number)
            self.slide.refresh_from_db()
            messages.success(request, saved_message(self.slide))
            return redirect(slide_url(self.project, self.slide))
        return self.render_forms(reading_form, values_form, reader_number=number)


class ReadingUpdateView(ReadingFormMixin, TemplateView):
    @cached_property
    def reading(self):
        reading = get_object_or_404(Reading, pk=self.kwargs["reading_pk"], slide=self.slide)
        if not access.can_edit_reading(self.request.user, self.slide, reading):
            raise PermissionDenied
        return reading

    def forms(self, data=None):
        reading_form = ReadingForm(
            data, instance=self.reading, project=self.project, user=self.request.user,
            exclude_reader_ids=other_reader_ids(self.slide, self.reading),
        )
        values_form = values_form_for(
            self.slide.smear_type, data=data, initial=None if data else self.reading.values
        )
        return reading_form, values_form

    def get(self, request, *args, **kwargs):
        reading_form, values_form = self.forms()
        return self.render_forms(reading_form, values_form, reading=self.reading,
                                 reader_number=self.reading.reader_number)

    def post(self, request, *args, **kwargs):
        reading_form, values_form = self.forms(request.POST)
        reading_ok = reading_form.is_valid()
        results = apply_calculations(values_form, self.slide.smear_type, self.project)
        if reading_ok and results is not None:
            save_reading(reading_form, values_form, results, self.slide, request.user, self.reading.reader_number)
            self.slide.refresh_from_db()
            messages.success(request, saved_message(self.slide))
            return redirect(slide_url(self.project, self.slide))
        return self.render_forms(reading_form, values_form, reading=self.reading,
                                 reader_number=self.reading.reader_number)


class SlideHistoryView(SlideMixin, DetailView):
    """History of the slide, its readings and its final result, newest first."""

    template_name = "core/history.html"

    def get_object(self):
        return self.get_slide()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        slide, user = self.object, self.request.user
        rows = [dict(row, record="Slide") for row in history_rows(slide)]
        hidden = 0
        for reading in slide.readings.all():
            if access.can_see_reading(user, slide, reading):
                rows += [dict(row, record=f"Reading (reader {reading.reader_number})") for row in history_rows(reading)]
            else:
                hidden += 1
        if slide.final:
            rows += [dict(row, record="Final result") for row in history_rows(slide.final)]
        rows.sort(key=lambda row: row["date"], reverse=True)
        context["record_label"] = f"Slide {slide}"
        context["back_url"] = slide_url(self.project, slide)
        context["rows"] = rows
        context["hidden_note"] = (
            f"{hidden} reading(s) by other readers are hidden until the slide's reading is complete." if hidden else ""
        )
        return context


RESULT_STATUS_FILTERS = [
    ("reading", "Awaiting reader 2"),
    ("discordant", "Awaiting tie-breaker"),
    ("final", "Final, not yet approved"),
    ("locked", "Approved and locked"),
]


def filter_results(qs, params):
    """Filters shared by the results list (and later, exports)."""
    if params.get("smear_type", "").isdigit():
        qs = qs.filter(smear_type_id=params["smear_type"])
    if params.get("result") in ("positive", "negative"):
        qs = qs.filter(final_result__is_positive=params["result"] == "positive")
    if params.get("species"):
        qs = qs.filter(final_result__species=params["species"])
    status = params.get("status")
    if status in ("reading", "discordant"):
        qs = qs.filter(status=status)
    elif status == "final":
        qs = qs.filter(final_result__isnull=False, final_result__locked=False)
    elif status == "locked":
        qs = qs.filter(final_result__locked=True)
    query = params.get("q", "").strip()
    if query:
        qs = qs.filter(
            Q(slide_id__icontains=query)
            | Q(sample__sample_id__icontains=query)
            | Q(sample__participant__study_participant_id__icontains=query)
        )
    return qs


class ResultsListView(ProjectAccessMixin, ListView):
    """All slides in a project with their final results, filterable."""

    template_name = "smears/results_list.html"
    context_object_name = "slides"
    paginate_by = 50

    def get_queryset(self):
        qs = self.project.slides.select_related("sample__participant", "smear_type", "final_result").order_by(
            "-created_at"
        )
        return filter_results(qs, self.request.GET)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["smear_types"] = SmearType.objects.filter(slides__project=self.project).distinct()
        context["species_choices"] = READING_SPECIES_CHOICES
        context["status_choices"] = RESULT_STATUS_FILTERS
        return context
