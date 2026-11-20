from django.db import transaction
from django.utils import timezone

from emergenciasTerritorialesAPP.ambito import verificar_ambito
from emergenciasTerritorialesAPP.models import ContactoEmergencia, ZonaRiesgo

from .models import DerivacionReporte, ReporteCiudadano


# ============================================================
# TRANSACCIÓN DEL NEGOCIO: DERIVACIÓN DEL REPORTE CIUDADANO
# ============================================================
# La usan la aplicación web y la API, para que ambas apliquen
# exactamente las mismas reglas.
#
# Cada operación ocurre dentro de una única transacción atómica:
#   1. se bloquea la fila del reporte (SELECT ... FOR UPDATE),
#   2. se vuelve a comprobar el ámbito por delegación con la fila
#      bloqueada (otro usuario pudo cambiarlo mientras tanto),
#   3. se validan zona y contacto contra la base,
#   4. se escribe el historial y se actualiza el reporte.
# Si cualquier paso falla, se revierte todo y el reporte queda igual.
#
#   Registrar  -> derivar_reporte()
#   Modificar  -> modificar_derivacion()
#   Eliminar   -> anular_derivacion() (baja lógica: queda en el historial)
#   Cerrar     -> resolver_reporte()


class ReglaNegocioError(Exception):
    """La operación es válida en forma, pero una regla del negocio la impide."""


def _bloquear_reporte(usuario, reporte_id):
    reporte = (
        ReporteCiudadano.objects.select_for_update()
        .filter(pk=reporte_id)
        .first()
    )

    if reporte is None:
        raise ReglaNegocioError("El reporte ya no existe.")

    verificar_ambito(usuario, reporte.delegacion_id)
    return reporte


def _validar_destino(reporte, zona_id, contacto_id):
    """Zona y contacto deben existir, estar activos y ser de la delegación."""
    zona = ZonaRiesgo.objects.filter(pk=zona_id).first()
    contacto = ContactoEmergencia.objects.filter(pk=contacto_id).first()

    if zona is None or not zona.activo:
        raise ReglaNegocioError("La zona de riesgo no existe o está dada de baja.")

    if contacto is None or not contacto.activo:
        raise ReglaNegocioError(
            "El contacto de emergencia no existe o está dado de baja."
        )

    if zona.delegacion_id != reporte.delegacion_id:
        raise ReglaNegocioError(
            "La zona de riesgo no pertenece a la delegación del reporte."
        )

    if contacto.delegacion_id != reporte.delegacion_id:
        raise ReglaNegocioError(
            "El contacto de emergencia no pertenece a la delegación del reporte."
        )

    return zona, contacto


def _validar_reporte_abierto(reporte):
    if not reporte.activo:
        raise ReglaNegocioError(
            "El reporte está dado de baja. Reactívelo antes de derivarlo."
        )

    if reporte.esta_resuelto:
        raise ReglaNegocioError(
            "El reporte ya está resuelto: no se puede derivar ni modificar."
        )


def derivar_reporte(usuario, reporte_id, zona_id, contacto_id, observacion=""):
    """Registra una derivación nueva; la anterior queda como historial."""
    with transaction.atomic():
        reporte = _bloquear_reporte(usuario, reporte_id)
        _validar_reporte_abierto(reporte)
        zona, contacto = _validar_destino(reporte, zona_id, contacto_id)

        reporte.derivaciones.filter(activo=True).update(activo=False)

        derivacion = DerivacionReporte.objects.create(
            reporte=reporte,
            zona=zona,
            contacto=contacto,
            observacion=(observacion or "").strip(),
            usuario=usuario,
        )

        reporte.zona = zona
        reporte.contacto = contacto
        reporte.estado = "derivado"
        reporte.save(update_fields=["zona", "contacto", "estado"])

    return derivacion


def _bloquear_derivacion_vigente(usuario, derivacion_id):
    derivacion = DerivacionReporte.objects.filter(pk=derivacion_id).first()

    if derivacion is None:
        raise ReglaNegocioError("La derivación ya no existe.")

    reporte = _bloquear_reporte(usuario, derivacion.reporte_id)

    # Se relee con el reporte bloqueado: otra persona pudo rederivarlo.
    derivacion = DerivacionReporte.objects.select_for_update().get(pk=derivacion_id)

    if not derivacion.activo:
        raise ReglaNegocioError(
            "Solo se puede operar la derivación vigente; esta ya es histórica."
        )

    return reporte, derivacion


def modificar_derivacion(
    usuario, derivacion_id, zona_id=None, contacto_id=None, observacion=None
):
    """Corrige la derivación vigente (zona, contacto u observación)."""
    with transaction.atomic():
        reporte, derivacion = _bloquear_derivacion_vigente(usuario, derivacion_id)
        _validar_reporte_abierto(reporte)

        zona, contacto = _validar_destino(
            reporte,
            zona_id or derivacion.zona_id,
            contacto_id or derivacion.contacto_id,
        )

        derivacion.zona = zona
        derivacion.contacto = contacto
        if observacion is not None:
            derivacion.observacion = observacion.strip()
        derivacion.save(update_fields=["zona", "contacto", "observacion"])

        reporte.zona = zona
        reporte.contacto = contacto
        reporte.save(update_fields=["zona", "contacto"])

    return derivacion


def anular_derivacion(usuario, derivacion_id):
    """
    Anula la derivación vigente (baja lógica: queda en el historial).
    El reporte vuelve a quedar pendiente, sin zona ni contacto.
    """
    with transaction.atomic():
        reporte, derivacion = _bloquear_derivacion_vigente(usuario, derivacion_id)
        _validar_reporte_abierto(reporte)

        derivacion.activo = False
        derivacion.anulada = True
        derivacion.save(update_fields=["activo", "anulada"])

        reporte.zona = None
        reporte.contacto = None
        reporte.estado = "pendiente"
        reporte.save(update_fields=["zona", "contacto", "estado"])

    return derivacion


def resolver_reporte(usuario, reporte_id):
    """Cierra un reporte derivado y registra la fecha de resolución."""
    with transaction.atomic():
        reporte = _bloquear_reporte(usuario, reporte_id)
        _validar_reporte_abierto(reporte)

        if reporte.estado != "derivado":
            raise ReglaNegocioError(
                "Solo se puede resolver un reporte que ya fue derivado."
            )

        reporte.estado = "resuelto"
        reporte.fecha_resolucion = timezone.now()
        reporte.save(update_fields=["estado", "fecha_resolucion"])

    return reporte
