from django.urls import path

from . import views


app_name = "beneficios"


urlpatterns = [
    path("ninos/", views.nino_lista, name="nino_lista"),
    path("ninos/nuevo/", views.nino_crear, name="nino_crear"),
    path("ninos/excel/", views.nino_exportar_excel, name="nino_exportar_excel"),
    path("ninos/<int:pk>/editar/", views.nino_editar, name="nino_editar"),
    path("ninos/<int:pk>/estado/", views.nino_cambiar_estado, name="nino_cambiar_estado"),

    path("campanas/", views.campana_lista, name="campana_lista"),
    path("campanas/nueva/", views.campana_crear, name="campana_crear"),
    path("campanas/<int:pk>/editar/", views.campana_editar, name="campana_editar"),
    path("campanas/<int:pk>/estado/", views.campana_cambiar_estado, name="campana_cambiar_estado"),
]
