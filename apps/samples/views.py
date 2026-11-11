from django.contrib import messages
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils.functional import cached_property
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from apps.core.history import history_rows
from apps.projects.mixins import ProjectAccessMixin

from .forms import ParticipantForm, SampleForm
from .models import Participant, Sample

# --- Participants -----------------------------------------------------------


class ParticipantMixin(ProjectAccessMixin):
    """Loads a participant that belongs to ``self.project``."""

    def get_participant(self, pk_kwarg="pk"):
        return get_object_or_404(Participant, pk=self.kwargs[pk_kwarg], project=self.project)


class ParticipantListView(ProjectAccessMixin, ListView):
    template_name = "samples/participant_list.html"
    context_object_name = "participants"
    paginate_by = 50

    def get_queryset(self):
        qs = self.project.participants.select_related("enrolment_site").annotate(
            sample_count=Count("samples")
        )
        query = self.request.GET.get("q", "").strip()
        if query:
            qs = qs.filter(study_participant_id__icontains=query)
        return qs


class ParticipantCreateView(ProjectAccessMixin, CreateView):
    required_permission = "enter_data"
    form_class = ParticipantForm
    template_name = "samples/participant_form.html"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["project"] = self.project
        return kwargs

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        response = super().form_valid(form)
        messages.success(self.request, f"Participant {self.object} registered.")
        return response

    def get_success_url(self):
        return reverse("samples:participant_detail", args=[self.project.code, self.object.pk])


class ParticipantDetailView(ParticipantMixin, DetailView):
    template_name = "samples/participant_detail.html"
    context_object_name = "participant"

    def get_object(self):
        return self.get_participant()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["samples"] = self.object.samples.select_related("site")
        return context


class ParticipantUpdateView(ParticipantMixin, UpdateView):
    required_permission = "enter_data"
    form_class = ParticipantForm
    template_name = "samples/participant_form.html"

    def get_object(self):
        return self.get_participant()

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["project"] = self.project
        return kwargs

    def form_valid(self, form):
        messages.success(self.request, "Participant details saved.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("samples:participant_detail", args=[self.project.code, self.object.pk])


class ParticipantHistoryView(ParticipantMixin, DetailView):
    template_name = "core/history.html"

    def get_object(self):
        return self.get_participant()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["record_label"] = f"Participant {self.object}"
        context["back_url"] = reverse("samples:participant_detail", args=[self.project.code, self.object.pk])
        context["rows"] = history_rows(self.object)
        return context


# --- Samples ----------------------------------------------------------------


class SampleMixin(ProjectAccessMixin):
    def get_sample(self):
        return get_object_or_404(
            Sample.objects.select_related("participant", "site"), pk=self.kwargs["pk"], project=self.project
        )


class SampleListView(ProjectAccessMixin, ListView):
    template_name = "samples/sample_list.html"
    context_object_name = "samples"
    paginate_by = 50

    def get_queryset(self):
        qs = self.project.samples.select_related("participant", "site")
        query = self.request.GET.get("q", "").strip()
        if query:
            qs = qs.filter(Q(sample_id__icontains=query) | Q(participant__study_participant_id__icontains=query))
        site = self.request.GET.get("site")
        if site:
            qs = qs.filter(site_id=site)
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["sites"] = self.project.sites.all()
        return context


class SampleCreateView(ParticipantMixin, CreateView):
    required_permission = "enter_data"
    form_class = SampleForm
    template_name = "samples/sample_form.html"

    @cached_property
    def participant(self):
        return self.get_participant("participant_pk")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["participant"] = self.participant
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["participant"] = self.participant
        return context

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        response = super().form_valid(form)
        messages.success(self.request, f"Sample {self.object} recorded for {self.participant}.")
        return response

    def get_success_url(self):
        return reverse("samples:participant_detail", args=[self.project.code, self.participant.pk])


class SampleDetailView(SampleMixin, DetailView):
    template_name = "samples/sample_detail.html"
    context_object_name = "sample"

    def get_object(self):
        return self.get_sample()


class SampleUpdateView(SampleMixin, UpdateView):
    required_permission = "enter_data"
    form_class = SampleForm
    template_name = "samples/sample_form.html"

    def get_object(self):
        return self.get_sample()

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["participant"] = self.object.participant
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["participant"] = self.object.participant
        return context

    def form_valid(self, form):
        messages.success(self.request, "Sample details saved.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("samples:sample_detail", args=[self.project.code, self.object.pk])


class SampleHistoryView(SampleMixin, DetailView):
    template_name = "core/history.html"

    def get_object(self):
        return self.get_sample()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["record_label"] = f"Sample {self.object}"
        context["back_url"] = reverse("samples:sample_detail", args=[self.project.code, self.object.pk])
        context["rows"] = history_rows(self.object)
        return context
