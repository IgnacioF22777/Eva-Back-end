from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied

from seguridadAPP.perfiles import SUPERVISOR, perfil_de
from tubo_gestionAPP.ambito import SIN_DELEGACION, delegacion_id_de, es_global


# ============================================================
# ÁMBITO DE LA MATRIZ: QUIÉN REGISTRA Y QUIÉN VE
# ============================================================
# Los permisos de Django dicen QUÉ puede hacer cada perfil; este módulo
# dice SOBRE QUÉ FUNCIONARIOS:
#
#   Administrador  -> todos los funcionarios.
#   Supervisor     -> (el delegado) los funcionarios de SU delegación,
#                     nunca a sí mismo: nadie registra sus propias
#                     ausencias, felicitaciones o reclamos.
#   Administrativo -> no registra; solo ve lo que le corresponde a él.
#
# Sin delegación asignada no se registra ni se ve nada (denegación por
# defecto), igual que en el tubo de compromisos.

PROPIO_REGISTRO = (
    "No puede registrar ausencias, felicitaciones ni reclamos para usted "
    "mismo: debe hacerlo su delegado."
)

FUERA_DE_AMBITO = (
    "El funcionario pertenece a otra delegación: solo el delegado de esa "
    "delegación puede registrar sus ausencias, felicitaciones o reclamos."
)

SOLO_DELEGADO = (
    "Solo el delegado (perfil Supervisor) de la delegación puede registrar "
    "ausencias, felicitaciones y reclamos."
)


def funcionarios_gestionables(usuario):
    """Funcionarios sobre los que el usuario puede registrar."""
    usuarios = get_user_model().objects.filter(
        is_active=True, perfil__isnull=False,
    ).select_related("perfil", "perfil__delegacion").order_by(
        "first_name", "last_name", "username",
    )

    if es_global(usuario):
        return usuarios

    if perfil_de(usuario) != SUPERVISOR:
        return usuarios.none()

    propia = delegacion_id_de(usuario)
    if propia is None:
        return usuarios.none()

    return usuarios.filter(perfil__delegacion_id=propia).exclude(pk=usuario.pk)


def verificar_puede_registrar(usuario, funcionario):
    """Lanza PermissionDenied (403) si no puede registrar sobre el funcionario."""
    if es_global(usuario):
        return

    if perfil_de(usuario) != SUPERVISOR:
        raise PermissionDenied(SOLO_DELEGADO)

    if funcionario.pk == usuario.pk:
        raise PermissionDenied(PROPIO_REGISTRO)

    propia = delegacion_id_de(usuario)
    if propia is None:
        raise PermissionDenied(SIN_DELEGACION)

    if delegacion_id_de(funcionario) != propia:
        raise PermissionDenied(FUERA_DE_AMBITO)


def registros_visibles(usuario, queryset):
    """
    Filtra ausencias o felicitaciones/reclamos según quién mira:
    el Administrador ve todo, el Supervisor su delegación y el resto
    solo lo suyo.
    """
    if es_global(usuario):
        return queryset

    if perfil_de(usuario) == SUPERVISOR:
        propia = delegacion_id_de(usuario)
        return queryset.filter(delegacion_id=propia) if propia else queryset.none()

    return queryset.filter(funcionario_id=usuario.pk)


def verificar_puede_ver(usuario, registro):
    """403 si el registro no está entre los que el usuario puede ver."""
    if not registros_visibles(usuario, type(registro).objects.filter(pk=registro.pk)).exists():
        raise PermissionDenied(
            "Este registro pertenece a otro funcionario o a otra delegación."
        )
