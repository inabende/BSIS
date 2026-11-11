from django.urls import path

from . import views

app_name = "smears"

urlpatterns = [
    path("samples/<int:sample_pk>/smears/new/", views.SmearRecordView.as_view(), name="smear_record"),
    path("smears/fields/", views.SmearFieldsView.as_view(), name="smear_fields"),
    path("results/", views.ResultsListView.as_view(), name="results"),
    path("slides/<int:pk>/", views.SlideDetailView.as_view(), name="slide_detail"),
    path("slides/<int:pk>/edit/", views.SlideUpdateView.as_view(), name="slide_update"),
    path("slides/<int:pk>/history/", views.SlideHistoryView.as_view(), name="slide_history"),
    path(
        "slides/<int:pk>/readings/<int:reading_pk>/edit/",
        views.ReadingUpdateView.as_view(),
        name="reading_update",
    ),
]
