from django.apps import apps
from django.contrib.auth.management import create_permissions
from django.contrib.auth.models import Group, Permission


# ============================================================
# PERFILES DEL SGR (RBAC CON GRUPOS Y PERMISOS DE DJANGO)
# ============================================================
# La pauta exige tres perfiles obligatorios:
#   Administrador  -> acceso total
#   Supervisor     -> acceso intermedio (operación y catálogos)
#   Administrativo -> acceso mínimo (consulta y registro)
#
# Cada perfil es un Group de Django. Los permisos se aplican en el
# servidor con @permission_required o con @perfil_requerido, siguiendo
# el principio de mínimo privilegio.

# Apps cuyos permisos se administran desde el SGR.
APPS_CON_PERMISOS = [
    "auth",
    "seguridadAPP",
    "delegacionesAPP",
    "tubo_gestionAPP",
    "sgr_maestrosAPP",
    "emergenciasTerritorialesAPP",
    "reportesCiudadanosAPP",
]

# Permisos de solo lectura sobre la operación municipal.
VER_OPERACION = [
    "delegacionesAPP.view_delegacion",
    "delegacionesAPP.view_servicio",
    "tubo_gestionAPP.view_compromiso",
    "tubo_gestionAPP.view_asignacioncompromiso",
    "tubo_gestionAPP.view_registroavance",
    "sgr_maestrosAPP.view_catalogoactividad",
    "sgr_maestrosAPP.view_periodo",
    "sgr_maestrosAPP.view_detalleperiodo",
    "sgr_maestrosAPP.view_meta",
]

ROLES = {
    # Acceso total: todos los permisos de las apps del proyecto.
    "Administrador": "*",

    # Supervisa la operación y parametriza catálogos, períodos y metas.
    "Supervisor": VER_OPERACION + [
        "auth.view_user",
        "delegacionesAPP.add_delegacion",
        "delegacionesAPP.change_delegacion",
        "delegacionesAPP.delete_delegacion",
        "delegacionesAPP.add_servicio",
        "delegacionesAPP.change_servicio",
        "delegacionesAPP.delete_servicio",
        "tubo_gestionAPP.add_compromiso",
        "tubo_gestionAPP.change_compromiso",
        "tubo_gestionAPP.delete_compromiso",
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

    # Acceso mínimo: consulta la operación y registra compromisos y avances.
    "Administrativo": VER_OPERACION + [
        "tubo_gestionAPP.add_compromiso",
        "tubo_gestionAPP.add_registroavance",
    ],
}

# Orden de precedencia: si un usuario quedara con más de un perfil,
# se conserva el de mayor privilegio (primero en este orden).
PERFILES = tuple(ROLES.keys())

# Equivalencia entre los roles históricos (6) y los tres perfiles.
# Se usa en la migración de datos 0002 para reasignar a los usuarios.
MAPEO_PERFILES = {
    "Administrador": "Administrador",
    "Coordinador": "Supervisor",
    "Delegado": "Supervisor",
    "Verificador": "Supervisor",
    "Funcionario": "Administrativo",
    "Consulta": "Administrativo",
}

# Roles que dejan de existir tras la migración.
ROLES_OBSOLETOS = [
    nombre for nombre in MAPEO_PERFILES if nombre not in PERFILES
]


def obtener_permiso(nombre_completo):
    app_label, codename = nombre_completo.split(".")

    return Permission.objects.filter(
        content_type__app_label=app_label,
        codename=codename
    ).first()


def permisos_del_proyecto():
    """Permisos que el SGR puede delegar (excluye la tabla de permisos)."""
    return Permission.objects.filter(
        content_type__app_label__in=APPS_CON_PERMISOS
    ).exclude(
        content_type__model="permission"
    )


def sincronizar_roles():
    """
    Crea los perfiles que no existan y les agrega sus permisos base.
    No quita permisos agregados manualmente desde la gestión de roles.
    Devuelve una lista de (perfil, creado, permisos_faltantes).
    """
    # Asegura que existan los permisos de todos los modelos.
    for app_config in apps.get_app_configs():
        create_permissions(app_config, verbosity=0)

    resultado = []

    for nombre_rol, permisos in ROLES.items():
        grupo, creado = Group.objects.get_or_create(name=nombre_rol)
        faltantes = []

        if permisos == "*":
            grupo.permissions.add(*permisos_del_proyecto())
        else:
            for nombre_permiso in permisos:
                permiso = obtener_permiso(nombre_permiso)

                if permiso is None:
                    faltantes.append(nombre_permiso)
                else:
                    grupo.permissions.add(permiso)

        resultado.append((nombre_rol, creado, faltantes))

    return resultado
