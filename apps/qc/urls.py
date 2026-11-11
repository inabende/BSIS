from django.urls import path

from . import views

app_name = "qc"

urlpatterns = [
    path("qc/review/", views.ReviewQueueView.as_view(), name="review"),
    path("qc/review/approve/", views.BulkApproveView.as_view(), name="bulk_approve"),
    path("qc/settings/", views.QCSettingsView.as_view(), name="settings"),
    path("slides/<int:pk>/lock/", views.LockView.as_view(), name="lock"),
    path("slides/<int:pk>/unlock/", views.UnlockView.as_view(), name="unlock"),
]
