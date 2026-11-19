from django.urls import path

from . import views


app_name = "reportes"

urlpatterns = [
    # Reportes ciudadanos
    path("", views.reporte_lista, name="reporte_lista"),
    path("nuevo/", views.reporte_crear, name="reporte_crear"),
    path("<int:pk>/", views.reporte_detalle, name="reporte_detalle"),
    path("<int:pk>/editar/", views.reporte_editar, name="reporte_editar"),
    path(
        "<int:pk>/estado/",
        views.reporte_cambiar_estado,
        name="reporte_cambiar_estado",
    ),

    # Transacción: derivación del reporte
    path("<int:pk>/derivar/", views.reporte_derivar, name="reporte_derivar"),
    path("<int:pk>/resolver/", views.reporte_resolver, name="reporte_resolver"),
    path(
        "derivaciones/<int:pk>/editar/",
        views.derivacion_editar,
        name="derivacion_editar",
    ),
    path(
        "derivaciones/<int:pk>/anular/",
        views.derivacion_anular,
        name="derivacion_anular",
    ),
]
