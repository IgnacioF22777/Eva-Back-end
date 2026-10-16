from django.contrib.auth.views import LogoutView
from django.urls import path
from . import views


app_name = "seguridad"


urlpatterns = [

    # ========================================================
    # ACCESO: INICIO Y CIERRE DE SESIÓN
    # ========================================================

    path(
        "login/",
        views.IniciarSesionView.as_view(),
        name="login"
    ),

    path(
        "logout/",
        LogoutView.as_view(),
        name="logout"
    ),

    # ========================================================
    # CRUD 1: USUARIOS
    # ========================================================

    path(
        "usuarios/",
        views.usuario_lista,
        name="usuario_lista"
    ),

    path(
        "usuarios/nuevo/",
        views.usuario_crear,
        name="usuario_crear"
    ),

    path(
        "usuarios/<int:pk>/editar/",
        views.usuario_editar,
        name="usuario_editar"
    ),

    path(
        "usuarios/<int:pk>/password/",
        views.usuario_password,
        name="usuario_password"
    ),

    path(
        "usuarios/<int:pk>/estado/",
        views.usuario_cambiar_estado,
        name="usuario_cambiar_estado"
    ),

    path(
        "usuarios/<int:pk>/eliminar/",
        views.usuario_eliminar,
        name="usuario_eliminar"
    ),

    # ========================================================
    # CRUD 2: ROLES (GRUPOS Y PERMISOS)
    # ========================================================

    path(
        "roles/",
        views.rol_lista,
        name="rol_lista"
    ),

    path(
        "roles/nuevo/",
        views.rol_crear,
        name="rol_crear"
    ),

    path(
        "roles/<int:pk>/editar/",
        views.rol_editar,
        name="rol_editar"
    ),

    path(
        "roles/<int:pk>/eliminar/",
        views.rol_eliminar,
        name="rol_eliminar"
    ),

]
