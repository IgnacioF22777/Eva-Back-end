from django.core.exceptions import ObjectDoesNotExist, PermissionDenied
from django.db.models import Q

from seguridadAPP.perfiles import ADMINISTRADOR, SUPERVISOR, perfil_de

from .validadores import verificar_ambito_delegacion


# ============================================================
# ÁMBITO TERRITORIAL: QUÉ COMPROMISOS VE Y OPERA CADA USUARIO
# ============================================================
# Los permisos de Django dicen QUÉ puede hacer un perfil; el ámbito dice
# SOBRE QUÉ DELEGACIÓN puede hacerlo:
#
#   Administrador  -> todas las delegaciones (visión global).
#   Supervisor     -> los compromisos de su delegación y los que aún no
#                     tienen delegación (para poder asignarlos). Solo
#                     puede asignar a servicios de su propia delegación.
#   Administrativo -> solo los compromisos de su delegación.
#
# Un Supervisor o Administrativo sin delegación asignada no ve ni opera
# compromisos (se deniega por defecto) hasta que el Administrador
# complete su perfil.

SIN_DELEGACION = (
    "Su usuario no tiene una delegación asignada. Solicite al "
    "administrador que complete su perfil."
)

FUERA_DE_AMBITO = (
    "El compromiso pertenece a otra delegación: su perfil solo puede "
    "operar los compromisos de su delegación."
)


def es_global(usuario):
    return perfil_de(usuario) == ADMINISTRADOR


def delegacion_id_de(usuario):
    try:
        return usuario.perfil.delegacion_id
    except (AttributeError, ObjectDoesNotExist):
        return None


def compromisos_visibles(usuario, queryset):
    """Filtra un queryset de Compromiso según el ámbito del usuario."""
    if es_global(usuario):
        return queryset

    delegacion_id = delegacion_id_de(usuario)

    if delegacion_id is None:
        return queryset.none()

    if perfil_de(usuario) == SUPERVISOR:
        return queryset.filter(
            Q(delegacion_id=delegacion_id) | Q(delegacion__isnull=True)
        )

    return queryset.filter(delegacion_id=delegacion_id)


def verificar_acceso_compromiso(usuario, compromiso):
    """Lanza PermissionDenied (403) si el compromiso está fuera de ámbito."""
    if es_global(usuario):
        return

    delegacion_id = delegacion_id_de(usuario)

    if delegacion_id is None:
        raise PermissionDenied(SIN_DELEGACION)

    if compromiso.delegacion_id is None and perfil_de(usuario) == SUPERVISOR:
        return

    try:
        verificar_ambito_delegacion(delegacion_id, compromiso.delegacion_id)
    except PermissionDenied:
        raise PermissionDenied(FUERA_DE_AMBITO)


def verificar_delegacion_destino(usuario, delegacion_id):
    """Un usuario sin visión global solo asigna a su propia delegación."""
    if es_global(usuario):
        return

    propia = delegacion_id_de(usuario)

    if propia is None:
        raise PermissionDenied(SIN_DELEGACION)

    try:
        verificar_ambito_delegacion(propia, delegacion_id)
    except PermissionDenied:
        raise PermissionDenied(
            "Solo puede asignar compromisos a servicios de su delegación."
        )
