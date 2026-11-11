from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin

from .models import Participant, Sample


@admin.register(Participant)
class ParticipantAdmin(SimpleHistoryAdmin):
    list_display = ("study_participant_id", "project", "sex", "enrolment_site", "enrolled_on")
    list_filter = ("project", "sex")
    search_fields = ("study_participant_id",)
    readonly_fields = ("created_by", "created_at", "updated_at")


@admin.register(Sample)
class SampleAdmin(SimpleHistoryAdmin):
    list_display = ("sample_id", "participant", "project", "visit", "collected_at", "site")
    list_filter = ("project", "site")
    search_fields = ("sample_id", "participant__study_participant_id")
    readonly_fields = ("project", "created_by", "created_at", "updated_at")
