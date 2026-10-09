"""
URL configuration for boss_project project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path, include
from django.views.generic import TemplateView  # serves a static HTML template

from connectors.mcp import endpoint as mcp_endpoint
from .refinement_views import asset, runtime_status, start_guide
from .version import VERSION
from . import auth_views

urlpatterns = [
    path('api/training/', include('training.urls')),
    path('api/crm/', include('crm.urls')),
    path('api/connectors/', include('connectors.urls')),
    # Read-only MCP for the owner's AI clients; off until a key is issued on the server (manage.py mcp_access).
    path('mcp/', mcp_endpoint, name='bos-mcp'),
    path("api/statements/", include("finance.statement_urls")),
    path('api/auth/csrf/', auth_views.csrf, name='bos-auth-csrf'),
    path('api/auth/login/', auth_views.login, name='bos-auth-login'),
    path('api/auth/logout/', auth_views.logout, name='bos-auth-logout'),
    path('api/auth/me/', auth_views.me, name='bos-auth-me'),
    path('api/auth/demo/', auth_views.demo, name='bos-auth-demo'),
    path("api/erp/", include("erp.urls")),
    path("api/operations/", include("operations.urls")),
    path("assets/<str:name>", asset),
    path('help/start.pdf', start_guide, name='bos-start-guide'),
    path("api/runtime/status/", runtime_status),
    # Root URL serves the React HTML — Django looks for it in TEMPLATES['DIRS']
    path('', TemplateView.as_view(template_name='boss_app_html.html', extra_context={'bos_version': VERSION})),

    path('admin/', admin.site.urls),
    # All URLs starting with 'api/' are handled by tasks/urls.py
    # e.g. /api/tasks/ → tasks/urls.py → TaskViewSet
    path('api/', include('tasks.urls')),
    path('api/', include('ai_assistant.urls')),
    path('api/', include('employees.urls')),
    path('api/', include('finance.urls')),
    path('api/', include('branches.urls')),
]

# Private files are served only by an authenticated object-scoped view.
