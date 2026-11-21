from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from delegacionesAPP.models import Servicio

from .ambito import verificar_acceso_compromiso, verificar_delegacion_destino
from .models import AdjuntoAvance, AsignacionCompromiso, Compromiso, RegistroAvance


# ============================================================
# TRANSACCIONES T1 Y T2 DEL TUBO DE GESTIÓN
# ============================================================
# Las usan la aplicación web (tubo_gestionAPP/views.py) y la API
# (api_asignaciones.py y api_avances.py), para que ambas apliquen las
# mismas reglas.
#
#   T1 - Asignación del compromiso (Supervisor)
#     Registrar -> asignar_compromiso()
#     Modificar -> corregir_asignacion()  (solo la observación)
#     Eliminar  -> anular_asignacion()    (baja lógica: queda en el historial)
#
#   T2 - Registro de avance (Administrativo)
#     Registrar -> registrar_avance()
#     Modificar -> corregir_avance()  (solo evidencia y observación)
#     Eliminar  -> anular_avance()    (baja lógica: queda en el historial)
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


# ============================================================
# T1: ASIGNACIÓN DEL COMPROMISO
# ============================================================

def asignar_compromiso(usuario, compromiso_id, delegacion_id, servicio_id, observacion=""):
    """
    Asigna un compromiso a una delegación y a un servicio de esa
    delegación:

      1. bloquea la fila del compromiso (SELECT ... FOR UPDATE),
      2. repite el control de ámbito con la fila bloqueada,
      3. revalida el servicio contra la base,
      4. deja la asignación vigente como historial (no se elimina),
      5. crea la nueva asignación y actualiza el compromiso.
    """
    with transaction.atomic():
        compromiso = _bloquear_compromiso(usuario, compromiso_id)
        verificar_delegacion_destino(usuario, delegacion_id)

        if not compromiso.activo:
            raise ValidationError(
                "No se puede asignar un compromiso dado de baja. Reactívelo primero."
            )

        # Revalidación contra la base, ya con la fila bloqueada: el
        # servicio pudo darse de baja entre la carga del formulario y el
        # envío.
        servicio = Servicio.objects.select_related("delegacion").filter(
            pk=servicio_id
        ).first()

        if servicio is None:
            raise ValidationError("El servicio seleccionado ya no existe.")

        if not servicio.activo or not servicio.delegacion.activo:
            raise ValidationError("El servicio seleccionado está dado de baja.")

        if servicio.delegacion_id != delegacion_id:
            raise ValidationError(
                "El servicio seleccionado no pertenece a la delegación."
            )

        AsignacionCompromiso.objects.filter(
            compromiso=compromiso, activo=True
        ).update(activo=False)

        asignacion = AsignacionCompromiso(
            compromiso=compromiso,
            delegacion_id=delegacion_id,
            servicio=servicio,
            usuario_asignador=usuario,
            observacion=(observacion or "").strip(),
        )
        asignacion.full_clean()
        asignacion.save()

        compromiso.delegacion_id = delegacion_id
        compromiso.servicio = servicio
        compromiso.save(update_fields=["delegacion", "servicio", "estado"])

    return asignacion, compromiso


def _bloquear_asignacion_vigente(usuario, asignacion_id):
    asignacion = AsignacionCompromiso.objects.filter(pk=asignacion_id).first()

    if asignacion is None:
        raise ValidationError("La asignación ya no existe.")

    compromiso = _bloquear_compromiso(usuario, asignacion.compromiso_id)
    asignacion = AsignacionCompromiso.objects.select_for_update().get(pk=asignacion_id)

    if asignacion.anulada:
        raise ValidationError("La asignación ya está anulada.")

    if not asignacion.activo:
        raise ValidationError(
            "Solo se puede modificar o anular la asignación vigente; las "
            "anteriores forman parte del historial."
        )

    if not compromiso.activo:
        raise ValidationError(
            "El compromiso está dado de baja: no se pueden modificar sus asignaciones."
        )

    return compromiso, asignacion


def corregir_asignacion(usuario, asignacion_id, observacion):
    """
    Corrige la observación de la asignación vigente. Para cambiar la
    delegación o el servicio se registra una nueva asignación, así el
    historial muestra la reasignación.
    """
    with transaction.atomic():
        compromiso, asignacion = _bloquear_asignacion_vigente(usuario, asignacion_id)
        asignacion.observacion = (observacion or "").strip()
        asignacion.full_clean()
        asignacion.save(update_fields=["observacion"])

    return asignacion, compromiso


def anular_asignacion(usuario, asignacion_id, motivo):
    """
    Anula la asignación vigente hecha por error (baja lógica). El
    compromiso vuelve a la asignación anterior no anulada o, si no hay
    otra, queda sin asignar.

    No se permite si ya hay avances vigentes registrados bajo esta
    asignación: primero deben anularse (T2), para no dejar avances de una
    delegación en un compromiso que pasa a otra.
    """
    motivo = (motivo or "").strip()

    if not motivo:
        raise ValidationError("Debe indicar el motivo de la anulación.")

    with transaction.atomic():
        compromiso, asignacion = _bloquear_asignacion_vigente(usuario, asignacion_id)

        if compromiso.avances.filter(
            anulado=False, fecha_registro__gte=asignacion.fecha_asignacion
        ).exists():
            raise ValidationError(
                "La asignación tiene avances registrados. Anule primero esos "
                "avances antes de anular la asignación."
            )

        asignacion.activo = False
        asignacion.anulada = True
        asignacion.motivo_anulacion = motivo
        asignacion.anulado_por = usuario
        asignacion.fecha_anulacion = timezone.now()
        asignacion.full_clean()
        asignacion.save(
            update_fields=[
                "activo",
                "anulada",
                "motivo_anulacion",
                "anulado_por",
                "fecha_anulacion",
            ]
        )

        anterior = compromiso.asignaciones.filter(anulada=False).exclude(
            pk=asignacion.pk
        ).order_by("-fecha_asignacion", "-pk").first()

        if anterior is not None:
            anterior.activo = True
            anterior.save(update_fields=["activo"])
            compromiso.delegacion_id = anterior.delegacion_id
            compromiso.servicio_id = anterior.servicio_id
        else:
            compromiso.delegacion = None
            compromiso.servicio = None

        compromiso.save(update_fields=["delegacion", "servicio", "estado"])

    return asignacion, compromiso


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
