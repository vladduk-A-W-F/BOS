from django.urls import path

from . import views


urlpatterns = [
    path('', views.index, name='crm-index'),
    path('deals/<int:deal_id>/', views.deal, name='crm-deal'),
    path('handoff/<uuid:training_public_id>/', views.handoff, name='crm-handoff'),
]
