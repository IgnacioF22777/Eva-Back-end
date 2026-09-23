from django.contrib import admin
from django.urls import path
from delegacionesAPP import views as vdelegaciones
urlpatterns = [
    path('lista/', vdelegaciones.delegaciones, name="lista"),
    path('', vdelegaciones.inicio,name="inicio"),
]
