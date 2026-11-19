from django.core.exceptions import PermissionDenied

from tubo_gestionAPP.ambito import SIN_DELEGACION, delegacion_id_de, es_global


# ============================================================
# ÁMBITO POR DELEGACIÓN (EMERGENCIAS Y REPORTES CIUDADANOS)
# ============================================================
# Misma regla que el Tubo de Gestión:
#
#   Administrador            -> todas las delegaciones.
#   Supervisor/Administrativo -> solo los registros de su delegación.
#   Sin delegación asignada   -> no ve nada (denegación por defecto).

FUERA_DE_AMBITO = (
    "El registro pertenece a otra delegación: su perfil solo puede "
    "operar los registros de su delegación."
)


def filtrar_por_ambito(usuario, queryset, campo="delegacion_id"):
    """Deja en el queryset solo lo que el usuario puede ver."""
    if es_global(usuario):
        return queryset

    delegacion_id = delegacion_id_de(usuario)

    if delegacion_id is None:
        return queryset.none()

    return queryset.filter(**{campo: delegacion_id})


def verificar_ambito(usuario, delegacion_id):
    """Lanza PermissionDenied (403) si la delegación no es la del usuario."""
    if es_global(usuario):
        return

    propia = delegacion_id_de(usuario)

    if propia is None:
        raise PermissionDenied(SIN_DELEGACION)

    if propia != delegacion_id:
        raise PermissionDenied(FUERA_DE_AMBITO)


def delegaciones_permitidas(usuario, queryset):
    """Delegaciones que el usuario puede elegir en un formulario."""
    return filtrar_por_ambito(usuario, queryset, campo="pk")
