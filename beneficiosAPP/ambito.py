from django.core.exceptions import PermissionDenied

from seguridadAPP.perfiles import SUPERVISOR, perfil_de
from tubo_gestionAPP.ambito import delegacion_id_de, es_global


# ============================================================
# ÁMBITO DE LOS REGALOS PARA NIÑOS
# ============================================================
#   Administrador  -> ve todas las delegaciones y administra campañas.
#   Supervisor     -> ve, inscribe, corrige y anula en su delegación.
#   Administrativo -> ve e inscribe en su delegación; corrige solo lo suyo.
# El RUT duplicado se busca en TODAS las delegaciones (models.py), pero
# el listado muestra solo los niños de la propia delegación.

SIN_DELEGACION = (
    "Su usuario no tiene una delegación asignada. Solicite al "
    "administrador que complete su perfil."
)


def ninos_visibles(usuario, queryset):
    if es_global(usuario):
        return queryset

    delegacion_id = delegacion_id_de(usuario)
    if delegacion_id is None:
        return queryset.none()

    return queryset.filter(delegacion_id=delegacion_id)


def verificar_puede_inscribir(usuario):
    """Devuelve la delegación con que se inscribe (la del usuario)."""
    delegacion_id = delegacion_id_de(usuario)
    if delegacion_id is None:
        raise PermissionDenied(SIN_DELEGACION)
    return delegacion_id


def verificar_puede_modificar(usuario, nino):
    if es_global(usuario):
        return

    if nino.delegacion_id != delegacion_id_de(usuario):
        raise PermissionDenied("El niño fue inscrito por otra delegación.")

    if perfil_de(usuario) != SUPERVISOR and nino.registrado_por_id != usuario.pk:
        raise PermissionDenied(
            "Solo puede corregir los niños que usted inscribió. "
            "Pida el cambio al delegado."
        )


def verificar_administra_campanas(usuario):
    if not es_global(usuario):
        raise PermissionDenied("Solo el Administrador administra las campañas.")
