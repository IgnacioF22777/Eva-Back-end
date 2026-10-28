from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied

from .roles import PERFILES


ADMINISTRADOR = "Administrador"
SUPERVISOR = "Supervisor"
ADMINISTRATIVO = "Administrativo"

ETIQUETAS = {
    ADMINISTRADOR: "Administrador",
    SUPERVISOR: "Supervisor",
    ADMINISTRATIVO: "Administrativo",
}

DESCRIPCIONES = {
    ADMINISTRADOR: "Acceso total al sistema",
    SUPERVISOR: "Supervisión operativa y catálogos",
    ADMINISTRATIVO: "Consulta y registro de información",
}


def perfil_de(usuario):
    """
    Devuelve el perfil del usuario (Administrador, Supervisor o
    Administrativo) o None si no tiene ninguno asignado.

    El superusuario siempre se considera Administrador para que nunca
    quede bloqueado fuera del sistema.
    """
    if usuario is None or not usuario.is_authenticated:
        return None

    if usuario.is_superuser:
        return ADMINISTRADOR

    nombres = set(usuario.groups.values_list("name", flat=True))

    for perfil in PERFILES:
        if perfil in nombres:
            return perfil

    return None


def perfil_requerido(*perfiles):
    """
    Restringe una vista a los perfiles indicados.

    - Si el usuario no ha iniciado sesión, lo redirige al login.
    - Si no tiene perfil, o su perfil no corresponde, responde 403.
    """
    permitidos = set(perfiles)

    def decorador(vista):
        @wraps(vista)
        def envoltura(request, *args, **kwargs):
            perfil = perfil_de(request.user)

            if perfil is None:
                raise PermissionDenied(
                    "Su usuario no tiene un perfil asignado. "
                    "Contacte al administrador del sistema."
                )

            if perfil not in permitidos:
                raise PermissionDenied(
                    "Su perfil no permite acceder a esta sección."
                )

            return vista(request, *args, **kwargs)

        return login_required(envoltura)

    return decorador
