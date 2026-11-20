from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .ambito import verificar_acceso_compromiso
from .models import AdjuntoAvance, Compromiso, RegistroAvance


# ============================================================
# TRANSACCIÓN 2 (T2): REGISTRO DE AVANCE DEL COMPROMISO
# ============================================================
# La usan la aplicación web (tubo_gestionAPP/views.py) y la API
# (tubo_gestionAPP/api_avances.py), para que ambas apliquen las mismas
# reglas.
#
#   Registrar -> registrar_avance()
#   Modificar -> corregir_avance()  (solo evidencia y observación)
#   Eliminar  -> anular_avance()    (baja lógica: queda en el historial)
#
# Cada operación ocurre en una única transacción atómica que bloquea la
# fila del compromiso (SELECT ... FOR UPDATE) y vuelve a comprobar el
# ámbito por delegación con la fila bloqueada. Las reglas del negocio
# que impiden la operación lanzan ValidationError.


def eliminar_archivos(storage, nombres):
    """Borra del disco los archivos de una transacción que se revirtió."""
    for nombre in nombres:
        try:
            storage.delete(nombre)
        except OSError:
            pass


def _bloquear_compromiso(usuario, compromiso_id):
    compromiso = Compromiso.objects.select_for_update().get(pk=compromiso_id)

    # Con la fila bloqueada se repite el control de ámbito: el compromiso
    # pudo reasignarse a otra delegación mientras tanto.
    verificar_acceso_compromiso(usuario, compromiso)
    return compromiso


def avance_vigente(compromiso):
    """Último avance no anulado del compromiso (o None)."""
    return compromiso.avances.filter(anulado=False).order_by(
        "-fecha_registro", "-pk"
    ).first()


def registrar_avance(
    usuario, compromiso_id, porcentaje, evidencia, observacion="", archivos=()
):
    """
    Registra un avance:

      1. bloquea la fila del compromiso,
      2. valida que esté activo y con asignación vigente,
      3. valida que el avance no retroceda,
      4. guarda el registro con su evidencia y sus archivos,
      5. actualiza el cumplimiento y el semáforo del compromiso.

    Si la transacción se revierte, también se borran del disco los
    archivos que alcanzaron a guardarse.
    """
    storage = AdjuntoAvance._meta.get_field("archivo").storage
    guardados = []

    try:
        with transaction.atomic():
            compromiso = _bloquear_compromiso(usuario, compromiso_id)

            if not compromiso.activo:
                raise ValidationError(
                    "No se puede registrar avance en un compromiso dado de baja."
                )

            if not compromiso.asignaciones.filter(activo=True).exists():
                raise ValidationError(
                    "El compromiso no tiene una asignación vigente. "
                    "Solicite al Supervisor que lo asigne antes de "
                    "registrar avances."
                )

            # Con la fila bloqueada, la comparación es confiable: ningún
            # otro usuario puede haber subido el cumplimiento entre la
            # validación y el guardado.
            if porcentaje < compromiso.cumplimiento:
                raise ValidationError(
                    "El avance no puede ser menor al cumplimiento actual "
                    f"({compromiso.cumplimiento}%). Si hubo un error, "
                    "registre la corrección con una observación que la "
                    "explique."
                )

            registro = RegistroAvance.objects.create(
                compromiso=compromiso,
                usuario_registro=usuario,
                porcentaje_avance=porcentaje,
                evidencia=evidencia,
                observacion=observacion or "",
            )

            for archivo in archivos:
                adjunto = AdjuntoAvance(
                    registro=registro,
                    nombre_original=archivo.name,
                    tamano=archivo.size,
                    tipo_contenido=(
                        getattr(archivo, "content_type", "") or ""
                    )[:100],
                )
                adjunto.archivo.save(archivo.name, archivo, save=False)
                guardados.append(adjunto.archivo.name)
                adjunto.save()

            compromiso.cumplimiento = registro.porcentaje_avance
            compromiso.save(update_fields=["cumplimiento", "estado"])

    except BaseException:
        eliminar_archivos(storage, guardados)
        raise

    return registro, compromiso


def _bloquear_avance_vigente(usuario, avance_id):
    avance = RegistroAvance.objects.filter(pk=avance_id).first()

    if avance is None:
        raise ValidationError("El registro de avance ya no existe.")

    compromiso = _bloquear_compromiso(usuario, avance.compromiso_id)
    avance = RegistroAvance.objects.select_for_update().get(pk=avance_id)

    if avance.anulado:
        raise ValidationError("El avance ya está anulado.")

    if not compromiso.activo:
        raise ValidationError(
            "El compromiso está dado de baja: no se pueden modificar sus avances."
        )

    vigente = avance_vigente(compromiso)
    if vigente is None or vigente.pk != avance.pk:
        raise ValidationError(
            "Solo se puede modificar o anular el último avance vigente del "
            "compromiso; los anteriores forman parte del historial."
        )

    return compromiso, avance


def corregir_avance(usuario, avance_id, evidencia=None, observacion=None):
    """
    Corrige la evidencia o la observación del último avance vigente.
    El porcentaje no se modifica: para cambiarlo se anula el avance y se
    registra uno nuevo, de modo que el historial muestre la corrección.
    """
    with transaction.atomic():
        compromiso, avance = _bloquear_avance_vigente(usuario, avance_id)

        if evidencia is not None:
            evidencia = evidencia.strip()
            if not evidencia:
                raise ValidationError("La evidencia del avance es obligatoria.")
            avance.evidencia = evidencia

        if observacion is not None:
            avance.observacion = observacion.strip()

        avance.full_clean()
        avance.save(update_fields=["evidencia", "observacion"])

    return avance, compromiso


def anular_avance(usuario, avance_id, motivo):
    """
    Anula el último avance vigente (baja lógica). El cumplimiento del
    compromiso vuelve al avance vigente anterior, o a 0 % si no hay otro.
    """
    motivo = (motivo or "").strip()

    if not motivo:
        raise ValidationError("Debe indicar el motivo de la anulación.")

    with transaction.atomic():
        compromiso, avance = _bloquear_avance_vigente(usuario, avance_id)

        avance.anulado = True
        avance.motivo_anulacion = motivo
        avance.anulado_por = usuario
        avance.fecha_anulacion = timezone.now()
        avance.full_clean()
        avance.save(
            update_fields=[
                "anulado",
                "motivo_anulacion",
                "anulado_por",
                "fecha_anulacion",
            ]
        )

        anterior = avance_vigente(compromiso)
        compromiso.cumplimiento = anterior.porcentaje_avance if anterior else 0
        compromiso.save(update_fields=["cumplimiento", "estado"])

    return avance, compromiso
