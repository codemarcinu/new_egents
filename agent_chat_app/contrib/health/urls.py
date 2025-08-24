from django.urls import path
from . import views

app_name = 'health'

urlpatterns = [
    path('health/', views.health_check, name='health_check'),
    path('ready/', views.readiness_probe, name='readiness_probe'),
    path('live/', views.liveness_probe, name='liveness_probe'),
    path('status/', views.system_status, name='system_status'),
]