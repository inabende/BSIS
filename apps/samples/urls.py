from django.urls import path

from . import views

app_name = "samples"

urlpatterns = [
    path("participants/", views.ParticipantListView.as_view(), name="participant_list"),
    path("participants/new/", views.ParticipantCreateView.as_view(), name="participant_create"),
    path("participants/<int:pk>/", views.ParticipantDetailView.as_view(), name="participant_detail"),
    path("participants/<int:pk>/edit/", views.ParticipantUpdateView.as_view(), name="participant_update"),
    path("participants/<int:pk>/history/", views.ParticipantHistoryView.as_view(), name="participant_history"),
    path(
        "participants/<int:participant_pk>/samples/new/",
        views.SampleCreateView.as_view(),
        name="sample_create",
    ),
    path("samples/", views.SampleListView.as_view(), name="sample_list"),
    path("samples/<int:pk>/", views.SampleDetailView.as_view(), name="sample_detail"),
    path("samples/<int:pk>/edit/", views.SampleUpdateView.as_view(), name="sample_update"),
    path("samples/<int:pk>/history/", views.SampleHistoryView.as_view(), name="sample_history"),
]
