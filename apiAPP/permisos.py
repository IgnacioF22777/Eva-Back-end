from rest_framework.exceptions import NotFound, PermissionDenied


# ============================================================
# PERMISOS DE LA API
# ============================================================
# La API usa exactamente los mismos permisos de Django que la aplicación
# web (asignados a los perfiles Administrador, Supervisor y
# Administrativo en seguridadAPP/roles.py). Así un perfil no puede hacer
# por la API algo que la web no le permite.
#
#   GET          -> view_<modelo>
#   POST         -> add_<modelo>
#   PUT / PATCH  -> change_<modelo>
#   DELETE       -> según la regla de la web (ver cada vista)

ACCION_POR_METODO = {
    "GET": "view",
    "HEAD": "view",
    "OPTIONS": "view",
    "POST": "add",
    "PUT": "change",
    "PATCH": "change",
    "DELETE": "delete",
}


def nombre_permiso(modelo, accion):
    """Ej.: (Delegacion, "view") -> "delegacionesAPP.view_delegacion"."""
    return f"{modelo._meta.app_label}.{accion}_{modelo._meta.model_name}"


def exigir_permiso(request, modelo, accion=None):
    """
    Responde 403 si el usuario no tiene el permiso de la acción.
    Sin `accion`, se deduce del método HTTP de la solicitud.
    """
    accion = accion or ACCION_POR_METODO[request.method]

    if not request.user.has_perm(nombre_permiso(modelo, accion)):
        raise PermissionDenied(
            "Su perfil no tiene permiso para realizar esta operación."
        )


def obtener_o_404(queryset, pk, mensaje):
    """Busca un registro por id o responde 404 con un mensaje en español."""
    try:
        return queryset.get(pk=pk)
    except queryset.model.DoesNotExist:
        raise NotFound(mensaje)
