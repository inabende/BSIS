from django.urls import path

from . import views

app_name = "reports"

urlpatterns = [
    path("search/", views.SearchView.as_view(), name="search"),
    path("search/export.<str:fmt>", views.ExportView.as_view(), name="export"),
    path("reports/", views.DashboardView.as_view(), name="dashboard"),
]
