from django.urls import path

from . import views


app_name = "organizaciones"


urlpatterns = [
    path("", views.organizacion_lista, name="organizacion_lista"),
    path("nueva/", views.organizacion_crear, name="organizacion_crear"),
    path("<int:pk>/editar/", views.organizacion_editar, name="organizacion_editar"),
    path("<int:pk>/verificar/", views.organizacion_verificar, name="organizacion_verificar"),
    path("<int:pk>/estado/", views.organizacion_cambiar_estado, name="organizacion_cambiar_estado"),
]
