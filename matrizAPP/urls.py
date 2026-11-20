from django.urls import path

from . import views


app_name = "matriz"


urlpatterns = [
    # Ausencias (R9)
    path("ausencias/", views.ausencia_lista, name="ausencia_lista"),
    path("ausencias/nueva/", views.ausencia_crear, name="ausencia_crear"),
    path("ausencias/<int:pk>/editar/", views.ausencia_editar, name="ausencia_editar"),
    path("ausencias/<int:pk>/estado/", views.ausencia_cambiar_estado, name="ausencia_cambiar_estado"),

    # Felicitaciones y reclamos (R8)
    path("felicitaciones-reclamos/", views.ajuste_lista, name="ajuste_lista"),
    path("felicitaciones-reclamos/nuevo/", views.ajuste_crear, name="ajuste_crear"),
    path("felicitaciones-reclamos/<int:pk>/editar/", views.ajuste_editar, name="ajuste_editar"),
    path("felicitaciones-reclamos/<int:pk>/estado/", views.ajuste_cambiar_estado, name="ajuste_cambiar_estado"),
    path("felicitaciones-reclamos/<int:pk>/respaldo/", views.ajuste_respaldo, name="ajuste_respaldo"),
]
