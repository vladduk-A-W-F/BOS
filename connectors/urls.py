from django.urls import path

from . import views

urlpatterns = [
    path('', views.index, name='connectors-index'),
    path('preview/', views.preview, name='connectors-preview'),
    path('create/', views.create, name='connectors-create'),
    path('sync-stale/', views.sync_stale, name='connectors-sync-stale'),
    path('<int:connector_id>/rows/', views.rows, name='connectors-rows'),
    path('<int:connector_id>/sync/', views.sync, name='connectors-sync'),
    path('<int:connector_id>/disable/', views.disable, name='connectors-disable'),
]
