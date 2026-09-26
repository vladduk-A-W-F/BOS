"""Server-only health routes plus the unchanged application URL structure."""
from django.urls import path
from boss_project.urls import urlpatterns as application_urls
from boss_project.server_health import liveness, readiness

urlpatterns = [
    path('health/live/', liveness, name='bos-health-live'),
    path('health/ready/', readiness, name='bos-health-ready'),
    *application_urls,
]
