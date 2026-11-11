from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from simple_history.admin import SimpleHistoryAdmin

from .models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin, SimpleHistoryAdmin):
    list_display = ("username", "first_name", "last_name", "email", "can_create_projects", "is_superuser", "is_active")
    list_filter = ("is_active", "is_superuser", "can_create_projects")
    fieldsets = BaseUserAdmin.fieldsets + (
        ("Blood smear system", {"fields": ("job_title", "can_create_projects")}),
    )

    def has_delete_permission(self, request, obj=None):
        # FR-21: accounts are deactivated, never deleted.
        return False
