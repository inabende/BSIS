from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

from apps.core.views import HomeView

admin.site.site_header = "Blood Smear System – Administration"
admin.site.site_title = "Blood Smear System"

urlpatterns = [
    path("", HomeView.as_view(), name="home"),
    path("login/", auth_views.LoginView.as_view(redirect_authenticated_user=True), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path(
        "password/change/",
        auth_views.PasswordChangeView.as_view(success_url="/"),
        name="password_change",
    ),
    path("projects/", include("apps.projects.urls")),
    path("projects/<slug:code>/", include("apps.samples.urls")),
    path("projects/<slug:code>/", include("apps.smears.urls")),
    path("projects/<slug:code>/", include("apps.qc.urls")),
    path("admin/", admin.site.urls),
]
