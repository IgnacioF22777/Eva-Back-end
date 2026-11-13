from django.urls import path

from . import views


app_name = "oficina_partes"


urlpatterns = [
    path("", views.carta_lista, name="carta_lista"),
    path("nueva/", views.carta_crear, name="carta_crear"),
    path("<int:pk>/editar/", views.carta_editar, name="carta_editar"),
    path("<int:pk>/estado/", views.carta_cambiar_estado, name="carta_cambiar_estado"),
]
