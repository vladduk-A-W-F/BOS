from django.urls import path

from . import views

# Подключается в boss_project/urls.py под префиксом 'api/'
urlpatterns = [
    path('branches/', views.branch_tree),
    path('dashboard/summary/', views.dashboard_summary),
    path('dashboard/helicopter/', views.dashboard_helicopter),
    path('dashboard/activity/', views.dashboard_activity),
]
