from django.urls import path
from . import views

urlpatterns = [
    path('content/', views.content),
    path('brochure.pdf', views.brochure),
    path('sessions/<str:case_id>/', views.state),
    path('sessions/<str:case_id>/<str:action>/', views.change),
]
