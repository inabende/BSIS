from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin

from .models import Project, ProjectMembership, Site


@admin.register(Site)
class SiteAdmin(SimpleHistoryAdmin):
    list_display = ("code", "name", "location", "is_active")
    list_filter = ("is_active",)
    search_fields = ("code", "name")


class MembershipInline(admin.TabularInline):
    model = ProjectMembership
    extra = 0
    autocomplete_fields = ["user"]


@admin.register(Project)
class ProjectAdmin(SimpleHistoryAdmin):
    list_display = ("code", "name", "principal_investigator", "status", "created_at")
    list_filter = ("status", "sites")
    search_fields = ("code", "name", "protocol_id", "principal_investigator")
    filter_horizontal = ("sites",)
    inlines = [MembershipInline]
    readonly_fields = ("created_by", "created_at", "updated_at")
