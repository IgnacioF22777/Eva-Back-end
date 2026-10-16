from django.apps import apps
from django.contrib.auth.management import create_permissions
from django.contrib.auth.models import Group, Permission


# ============================================================
# ROLES DEL SGR (RBAC CON GRUPOS Y PERMISOS DE DJANGO)
# ============================================================
# Cada rol corresponde a un actor de la guía del proyecto y se
# implementa como un Group de Django. Los permisos usan el formato
# "app_label.codename" y se aplican en el servidor con
# @permission_required, siguiendo el principio de mínimo privilegio.

VER_OPERACION = [
    "delegacionesAPP.view_delegacion",
    "delegacionesAPP.view_servicio",
    "tubo_gestionAPP.view_compromiso",
    "sgr_maestrosAPP.view_catalogoactividad",
    "sgr_maestrosAPP.view_periodo",
    "sgr_maestrosAPP.view_detalleperiodo",
    "sgr_maestrosAPP.view_meta",
]

ROLES = {
    # Configura delegaciones, usuarios, cargos, catálogos y permisos.
    "Administrador": VER_OPERACION + [
        "auth.view_user",
        "auth.add_user",
        "auth.change_user",
        "auth.delete_user",
        "auth.view_group",
        "auth.add_group",
        "auth.change_group",
        "auth.delete_group",
        "seguridadAPP.view_perfilusuario",
        "seguridadAPP.add_perfilusuario",
        "seguridadAPP.change_perfilusuario",
        "seguridadAPP.delete_perfilusuario",
        "delegacionesAPP.add_delegacion",
        "delegacionesAPP.change_delegacion",
    ],

    # Supervisa la operación, parametriza catálogos, períodos y metas.
    "Coordinador": VER_OPERACION + [
        "auth.view_user",
        "sgr_maestrosAPP.add_catalogoactividad",
        "sgr_maestrosAPP.change_catalogoactividad",
        "sgr_maestrosAPP.add_periodo",
        "sgr_maestrosAPP.change_periodo",
        "sgr_maestrosAPP.add_detalleperiodo",
        "sgr_maestrosAPP.change_detalleperiodo",
        "sgr_maestrosAPP.delete_detalleperiodo",
        "sgr_maestrosAPP.add_meta",
        "sgr_maestrosAPP.change_meta",
    ],

    # Consulta la gestión de su delegación y revisa compromisos.
    "Delegado": VER_OPERACION + [
        "auth.view_user",
        "tubo_gestionAPP.change_compromiso",
    ],

    # Registra actividades y compromisos.
    "Funcionario": VER_OPERACION + [
        "tubo_gestionAPP.add_compromiso",
        "tubo_gestionAPP.change_compromiso",
    ],

    # Revisa y valida registros.
    "Verificador": VER_OPERACION,

    # Solo consulta tableros e informes.
    "Consulta": VER_OPERACION,
}


def obtener_permiso(nombre_completo):
    app_label, codename = nombre_completo.split(".")

    return Permission.objects.filter(
        content_type__app_label=app_label,
        codename=codename
    ).first()


def sincronizar_roles():
    """
    Crea los roles que no existan y les agrega sus permisos base.
    No quita permisos agregados manualmente desde la gestión de roles.
    Devuelve una lista de (rol, creado, permisos_faltantes).
    """
    # Asegura que existan los permisos de todos los modelos.
    for app_config in apps.get_app_configs():
        create_permissions(app_config, verbosity=0)

    resultado = []

    for nombre_rol, permisos in ROLES.items():
        grupo, creado = Group.objects.get_or_create(name=nombre_rol)
        faltantes = []

        for nombre_permiso in permisos:
            permiso = obtener_permiso(nombre_permiso)

            if permiso is None:
                faltantes.append(nombre_permiso)
            else:
                grupo.permissions.add(permiso)

        resultado.append((nombre_rol, creado, faltantes))

    return resultado
