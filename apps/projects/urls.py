from django.urls import path

from . import views

app_name = "projects"

urlpatterns = [
    path("", views.ProjectListView.as_view(), name="list"),
    path("new/", views.ProjectCreateView.as_view(), name="create"),
    path("<slug:code>/", views.ProjectDetailView.as_view(), name="detail"),
    path("<slug:code>/edit/", views.ProjectUpdateView.as_view(), name="update"),
    path("<slug:code>/status/", views.ProjectStatusView.as_view(), name="status"),
    path("<slug:code>/history/", views.ProjectHistoryView.as_view(), name="history"),
    path("<slug:code>/members/add/", views.MemberAddView.as_view(), name="member_add"),
    path("<slug:code>/members/<int:pk>/role/", views.MemberRoleView.as_view(), name="member_role"),
    path("<slug:code>/members/<int:pk>/remove/", views.MemberRemoveView.as_view(), name="member_remove"),
]
