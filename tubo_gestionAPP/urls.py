from django.contrib import admin
from django.urls import path
from tubo_gestionAPP import views as vtubo_gestion
urlpatterns = [
    path('tablero_metas/',vtubo_gestion.tablero_metas,name="tablero_metas"),
    path('', vtubo_gestion.inicio,name="home_gestion")
]
