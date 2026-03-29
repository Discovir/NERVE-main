from django.urls import path
from core_app.api import api
from core_app import views
from django.contrib import admin

urlpatterns = [
    # Django Ninja REST API — auto-docs at /api/docs
    path('admin/', admin.site.urls),
    path("api/", api.urls),
    path("", views.home, name="home"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("enroll/", views.enroll, name="enroll"),
    path("verify/", views.verify, name="verify"),
]