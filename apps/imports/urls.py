from django.urls import path

from . import views

app_name = "imports"

urlpatterns = [
    path("imports/", views.ImportListView.as_view(), name="list"),
    path("imports/new/", views.ImportUploadView.as_view(), name="upload"),
    path("imports/template/<int:smear_type_pk>.xlsx", views.TemplateDownloadView.as_view(), name="template"),
    path("imports/<int:pk>/columns/", views.ImportMapView.as_view(), name="map"),
    path("imports/<int:pk>/", views.ImportPreviewView.as_view(), name="preview"),
    path("imports/<int:pk>/cancel/", views.ImportCancelView.as_view(), name="cancel"),
    path("imports/<int:pk>/problems.csv", views.ImportProblemsCSV.as_view(), name="problems"),
    path("imports/<int:pk>/file/", views.ImportFileView.as_view(), name="file"),
]
