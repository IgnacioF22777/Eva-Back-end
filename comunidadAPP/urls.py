from django.urls import path

from . import views


app_name = "comunidad"


urlpatterns = [
    # Territorios
    path("territorios/", views.territorio_lista, name="territorio_lista"),
    path("territorios/nuevo/", views.territorio_crear, name="territorio_crear"),
    path("territorios/<int:pk>/editar/", views.territorio_editar, name="territorio_editar"),
    path("territorios/<int:pk>/estado/", views.territorio_cambiar_estado, name="territorio_cambiar_estado"),

    # Vecinos
    path("vecinos/", views.vecino_lista, name="vecino_lista"),
    path("vecinos/nuevo/", views.vecino_crear, name="vecino_crear"),
    path("vecinos/buscar/", views.vecino_buscar, name="vecino_buscar"),
    path("vecinos/<int:pk>/editar/", views.vecino_editar, name="vecino_editar"),
    path("vecinos/<int:pk>/estado/", views.vecino_cambiar_estado, name="vecino_cambiar_estado"),

    # Membresía y dirigencia en juntas de vecinos
    path("organizaciones/<int:organizacion_pk>/miembros/", views.membresia_lista, name="membresia_lista"),
    path("organizaciones/<int:organizacion_pk>/miembros/nuevo/", views.membresia_crear, name="membresia_crear"),
    path("miembros/<int:pk>/editar/", views.membresia_editar, name="membresia_editar"),
    path("miembros/<int:pk>/cerrar/", views.membresia_cerrar, name="membresia_cerrar"),

    # Hitos
    path("hitos/", views.hito_lista, name="hito_lista"),
    path("hitos/nuevo/", views.hito_crear, name="hito_crear"),
    path("hitos/<int:pk>/editar/", views.hito_editar, name="hito_editar"),
    path("hitos/<int:pk>/estado/", views.hito_cambiar_estado, name="hito_cambiar_estado"),
]
