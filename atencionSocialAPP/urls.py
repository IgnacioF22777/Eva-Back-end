from django.urls import path

from . import views


app_name = "atencion_social"


urlpatterns = [
    path("", views.atencion_lista, name="atencion_lista"),
    path("nueva/", views.atencion_crear, name="atencion_crear"),
    path("<int:pk>/editar/", views.atencion_editar, name="atencion_editar"),
    path("<int:pk>/estado/", views.atencion_cambiar_estado, name="atencion_cambiar_estado"),
]
