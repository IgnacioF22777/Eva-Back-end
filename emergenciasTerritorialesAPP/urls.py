from django.urls import path

from . import views


app_name = "emergencias"

urlpatterns = [
    # Mantenedor 1: zonas de riesgo
    path("zonas/", views.zona_lista, name="zona_lista"),
    path("zonas/nueva/", views.zona_crear, name="zona_crear"),
    path("zonas/<int:pk>/editar/", views.zona_editar, name="zona_editar"),
    path(
        "zonas/<int:pk>/estado/",
        views.zona_cambiar_estado,
        name="zona_cambiar_estado",
    ),

    # Mantenedor 2: contactos de emergencia
    path("contactos/", views.contacto_lista, name="contacto_lista"),
    path("contactos/nuevo/", views.contacto_crear, name="contacto_crear"),
    path(
        "contactos/<int:pk>/editar/",
        views.contacto_editar,
        name="contacto_editar",
    ),
    path(
        "contactos/<int:pk>/estado/",
        views.contacto_cambiar_estado,
        name="contacto_cambiar_estado",
    ),
]
