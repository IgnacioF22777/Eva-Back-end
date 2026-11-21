from django.urls import path

from . import views
from . import views_tipos


app_name = "atencion_social"


urlpatterns = [
    path("", views.atencion_lista, name="atencion_lista"),
    path("nueva/", views.atencion_crear, name="atencion_crear"),
    path("<int:pk>/editar/", views.atencion_editar, name="atencion_editar"),
    path("<int:pk>/estado/", views.atencion_cambiar_estado, name="atencion_cambiar_estado"),

    # EVA 3: mantenedor de tipos y subtipos de atención social.
    path("tipos/", views_tipos.tipo_lista, name="tipo_lista"),
    path("tipos/nuevo/", views_tipos.tipo_crear, name="tipo_crear"),
    path("tipos/<int:pk>/editar/", views_tipos.tipo_editar, name="tipo_editar"),
    path("tipos/<int:pk>/estado/", views_tipos.tipo_cambiar_estado, name="tipo_cambiar_estado"),
    path("subtipos/nuevo/", views_tipos.subtipo_crear, name="subtipo_crear"),
    path("subtipos/<int:pk>/editar/", views_tipos.subtipo_editar, name="subtipo_editar"),
    path("subtipos/<int:pk>/estado/", views_tipos.subtipo_cambiar_estado, name="subtipo_cambiar_estado"),
]
