
from django.apps import apps
from django.contrib.auth.management import create_permissions
from django.contrib.auth.models import Group, Permission


# ============================================================
# PERFILES DEL SGR
# ============================================================
# Administrador: acceso total.
# Supervisor: supervisión y gestión.
# Administrativo: consulta y registro operativo.

APPS_CON_PERMISOS = [
    "auth",
    "seguridadAPP",
    "delegacionesAPP",
    "tubo_gestionAPP",
    "matrizAPP",
    "sgr_maestrosAPP",
    "emergenciasTerritorialesAPP",
    "reportesCiudadanosAPP",
    "organizacionesAPP",
    "oficinaPartesAPP",
    "atencionSocialAPP",
    "actividadesAPP",
]


# Permisos de consulta de la operación municipal.
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
    "organizacionesAPP.view_organizacioncomunitaria",
    "oficinaPartesAPP.view_cartaoficinapartes",
    "atencionSocialAPP.view_atencionsocial",

    # EVA 3: actividades diarias.
    "actividadesAPP.view_registroactividad",

    # Back End: emergencias territoriales y reportes ciudadanos.
    "emergenciasTerritorialesAPP.view_zonariesgo",
    "emergenciasTerritorialesAPP.view_contactoemergencia",
    "reportesCiudadanosAPP.view_reporteciudadano",
    "reportesCiudadanosAPP.view_derivacionreporte",
]


ROLES = {
    # Administrador: todos los permisos de las apps del SGR.
    "Administrador": "*",

    # Supervisor: mantenedores y actividades diarias.
    "Supervisor": VER_OPERACION + [
        "auth.view_user",
        "organizacionesAPP.add_organizacioncomunitaria",
        "organizacionesAPP.change_organizacioncomunitaria",
        "organizacionesAPP.delete_organizacioncomunitaria",
        "oficinaPartesAPP.add_cartaoficinapartes",
        "oficinaPartesAPP.change_cartaoficinapartes",
        "oficinaPartesAPP.delete_cartaoficinapartes",
        "atencionSocialAPP.add_atencionsocial",
        "atencionSocialAPP.change_atencionsocial",
        "atencionSocialAPP.delete_atencionsocial",

        "delegacionesAPP.add_servicio",
        "delegacionesAPP.change_servicio",
        "delegacionesAPP.delete_servicio",

        "tubo_gestionAPP.add_compromiso",
        "tubo_gestionAPP.change_compromiso",
        "tubo_gestionAPP.delete_compromiso",

        # T2: el Supervisor corrige o anula el último avance (no lo
        # registra: eso lo hace el Administrativo).
        "tubo_gestionAPP.change_registroavance",
        "tubo_gestionAPP.delete_registroavance",

        "sgr_maestrosAPP.add_catalogoactividad",
        "sgr_maestrosAPP.change_catalogoactividad",

        "sgr_maestrosAPP.add_periodo",
        "sgr_maestrosAPP.change_periodo",

        "sgr_maestrosAPP.add_detalleperiodo",
        "sgr_maestrosAPP.change_detalleperiodo",
        "sgr_maestrosAPP.delete_detalleperiodo",

        "sgr_maestrosAPP.add_meta",
        "sgr_maestrosAPP.change_meta",

        # EVA 3: actividades.
        "actividadesAPP.add_registroactividad",
        "actividadesAPP.change_registroactividad",
        "actividadesAPP.delete_registroactividad",

        # Matriz SGR (Eva 3): el delegado registra ausencias (R9) y
        # felicitaciones o reclamos (R8) de los funcionarios de su
        # delegación. El ámbito se controla en matrizAPP/ambito.py.
        "matrizAPP.view_ausencia",
        "matrizAPP.add_ausencia",
        "matrizAPP.change_ausencia",
        "matrizAPP.view_ajustedesempeno",
        "matrizAPP.add_ajustedesempeno",
        "matrizAPP.change_ajustedesempeno",

        # Back End: mantenedores de emergencias de su delegación.
        "emergenciasTerritorialesAPP.add_zonariesgo",
        "emergenciasTerritorialesAPP.change_zonariesgo",
        "emergenciasTerritorialesAPP.delete_zonariesgo",

        "emergenciasTerritorialesAPP.add_contactoemergencia",
        "emergenciasTerritorialesAPP.change_contactoemergencia",
        "emergenciasTerritorialesAPP.delete_contactoemergencia",

        # Back End: reportes ciudadanos y transacción de derivación.
        "reportesCiudadanosAPP.add_reporteciudadano",
        "reportesCiudadanosAPP.change_reporteciudadano",
        "reportesCiudadanosAPP.delete_reporteciudadano",

        "reportesCiudadanosAPP.add_derivacionreporte",
        "reportesCiudadanosAPP.change_derivacionreporte",
        "reportesCiudadanosAPP.delete_derivacionreporte",
    ],

    # Administrativo: consulta, ingreso y edición.
    "Administrativo": VER_OPERACION + [
        # Matriz SGR (Eva 3): el funcionario solo CONSULTA sus propias
        # ausencias, felicitaciones y reclamos; no puede registrarlos.
        "matrizAPP.view_ausencia",
        "matrizAPP.view_ajustedesempeno",
        "tubo_gestionAPP.add_compromiso",
        "tubo_gestionAPP.add_registroavance",
        # Descriptor: el Apoyo Administrativo registra las solicitudes que
        # llegan por carta y Oficina de Partes.
        "oficinaPartesAPP.add_cartaoficinapartes",
        "oficinaPartesAPP.change_cartaoficinapartes",

        # EVA 3: el Gestor Social registra sus atenciones (sin dar de baja).
        "atencionSocialAPP.add_atencionsocial",
        "atencionSocialAPP.change_atencionsocial",

        # EVA 3: actividades propias.
        "actividadesAPP.add_registroactividad",
        "actividadesAPP.change_registroactividad",

        # Back End: registra los reportes que informan los vecinos.
        "reportesCiudadanosAPP.add_reporteciudadano",
    ],
}


# ============================================================
# COMPATIBILIDAD CON PERFILES ANTERIORES
# ============================================================

# Permisos que un rol tuvo en versiones anteriores y ya no debe tener.
# sincronizar_roles() no quita permisos en general (para no borrar los
# que el Administrador asignó a mano), pero estos se retiran siempre
# porque eran un error de seguridad: un Supervisor podía crear, editar
# o dar de baja delegaciones que no son la suya.
PERMISOS_RETIRADOS = {
    "Supervisor": [
        "delegacionesAPP.add_delegacion",
        "delegacionesAPP.change_delegacion",
        "delegacionesAPP.delete_delegacion",
    ],
}


PERFILES = tuple(ROLES.keys())

MAPEO_PERFILES = {
    "Administrador": "Administrador",
    "Coordinador": "Supervisor",
    "Delegado": "Supervisor",
    "Verificador": "Supervisor",
    "Funcionario": "Administrativo",
    "Consulta": "Administrativo",
}

ROLES_OBSOLETOS = [
    nombre
    for nombre in MAPEO_PERFILES
    if nombre not in PERFILES
]


# ============================================================
# FUNCIONES DE PERMISOS
# ============================================================

def obtener_permiso(nombre_completo):
    app_label, codename = nombre_completo.split(".")

    return Permission.objects.filter(
        content_type__app_label=app_label,
        codename=codename,
    ).first()


def permisos_del_proyecto():
    """Permisos administrables del sistema SGR."""
    return Permission.objects.filter(
        content_type__app_label__in=APPS_CON_PERMISOS
    ).exclude(
        content_type__model="permission"
    )


def sincronizar_roles():
    """
    Crea los grupos necesarios y agrega permisos faltantes.
    No elimina permisos previamente asignados.
    """

    for app_config in apps.get_app_configs():
        create_permissions(app_config, verbosity=0)

    resultado = []

    for nombre_rol, permisos in ROLES.items():
        grupo, creado = Group.objects.get_or_create(
            name=nombre_rol
        )

        faltantes = []

        if permisos == "*":
            grupo.permissions.add(
                *permisos_del_proyecto()
            )

        else:
            for nombre_permiso in permisos:
                permiso = obtener_permiso(nombre_permiso)

                if permiso is None:
                    faltantes.append(nombre_permiso)
                else:
                    grupo.permissions.add(permiso)

        for nombre_permiso in PERMISOS_RETIRADOS.get(nombre_rol, []):
            permiso = obtener_permiso(nombre_permiso)

            if permiso is not None:
                grupo.permissions.remove(permiso)

        resultado.append(
            (nombre_rol, creado, faltantes)
        )

    return resultado
