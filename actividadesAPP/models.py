import os
import re
import uuid
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils import timezone


ZONA_CHILE = ZoneInfo("America/Santiago")


def normalizar_telefono(numero):
    """Deja nueve dígitos chilenos sin el prefijo internacional +56."""
    digitos = re.sub(r"\D", "", numero or "")
    if digitos.startswith("56") and len(digitos) == 11:
        digitos = digitos[2:]
    return digitos


def nombre_comparable(nombre):
    return " ".join((nombre or "").casefold().split())


def fecha_cierre_semana(fecha):
    """La actividad de lunes a domingo puede ingresarse hasta el lunes siguiente."""
    lunes_esta_semana = fecha - timedelta(days=fecha.weekday())
    return lunes_esta_semana + timedelta(days=7)


# ============================================================
# EVIDENCIA DEL REGISTRO (pauta: verificación de actividades y evidencias)
# ============================================================

EXTENSIONES_EVIDENCIA = {".pdf", ".jpg", ".jpeg", ".png"}
MAX_MB_EVIDENCIA = 10

MENSAJE_APROBADO = "Un registro aprobado no se puede modificar."


def ruta_evidencia(instancia, nombre):
    """Nombre aleatorio: el nombre original no se usa en el disco."""
    extension = os.path.splitext(nombre)[1].lower()
    return f"actividades/evidencias/{timezone.now():%Y/%m}/{uuid.uuid4().hex}{extension}"


def validar_evidencia(archivo):
    extension = os.path.splitext(archivo.name)[1].lower()
    if extension not in EXTENSIONES_EVIDENCIA:
        raise ValidationError("La evidencia debe ser PDF, JPG o PNG.")
    if archivo.size == 0:
        raise ValidationError("El archivo de evidencia está vacío.")
    if archivo.size > MAX_MB_EVIDENCIA * 1024 * 1024:
        raise ValidationError(f"La evidencia no puede superar {MAX_MB_EVIDENCIA} MB.")


def validar_rut_opcional(rut):
    from tubo_gestionAPP.validadores import validar_rut_chileno

    if rut:
        validar_rut_chileno(rut)


def rango_dia_chile(fecha):
    """Límites [inicio, fin) del día local (sin conversión SQL por zona)."""
    inicio = datetime.combine(fecha, time.min, tzinfo=ZONA_CHILE)
    fin = datetime.combine(fecha + timedelta(days=1), time.min, tzinfo=ZONA_CHILE)
    return inicio, fin


class RegistroActividad(models.Model):
    # Flujo de verificación (pauta Eva 3): el delegado revisa cada registro.
    PENDIENTE = "PENDIENTE"
    APROBADA = "APROBADA"
    RECHAZADA = "RECHAZADA"
    ANTECEDENTES = "ANTECEDENTES"
    ESTADOS_VERIFICACION = [
        (PENDIENTE, "Pendiente"),
        (APROBADA, "Aprobada"),
        (RECHAZADA, "Rechazada"),
        (ANTECEDENTES, "Solicitud de más antecedentes"),
    ]

    # Tubo de seguimiento de la delegación.
    TUBO_EN_PROCESO = "EN_PROCESO"
    TUBO_DERIVADO = "DERIVADO"
    TUBO_SOLUCIONADO = "SOLUCIONADO"
    TUBO_NO_APLICA = "NO_APLICA"
    ESTADOS_TUBO = [
        (TUBO_EN_PROCESO, "En proceso"),
        (TUBO_DERIVADO, "Derivado"),
        (TUBO_SOLUCIONADO, "Solucionado"),
        (TUBO_NO_APLICA, "No aplica"),
    ]

    TIPO_VECINO = "VECINO"
    TIPO_DELEGADO = "DELEGADO"
    TIPOS_SOLICITANTE = [
        (TIPO_VECINO, "Vecino/a o usuario/a"),
        (TIPO_DELEGADO, "Delegado/a"),
    ]

    funcionario = models.ForeignKey(
        "seguridadAPP.PerfilUsuario",
        on_delete=models.PROTECT,
        related_name="actividades_registradas",
        verbose_name="Funcionario que registra",
    )
    actividad = models.ForeignKey(
        "sgr_maestrosAPP.CatalogoActividad",
        on_delete=models.PROTECT,
        related_name="registros_diarios",
        verbose_name="Actividad del catálogo",
    )
    fecha_actividad = models.DateField(verbose_name="Fecha de la actividad")
    solicitante_tipo = models.CharField(
        max_length=12,
        choices=TIPOS_SOLICITANTE,
        default=TIPO_VECINO,
        verbose_name="Tipo de solicitante",
    )
    nombre_usuario = models.CharField(
        max_length=150,
        blank=True,
        verbose_name="Nombre del usuario/a",
    )
    telefono_usuario = models.CharField(
        max_length=24,
        blank=True,
        verbose_name="Teléfono del usuario/a",
    )
    detalle = models.TextField(blank=True, max_length=1000)
    fecha_ingreso = models.DateTimeField(
        default=timezone.now,
        editable=False,
        db_index=True,
        verbose_name="Fecha y hora del ingreso",
    )
    puntua = models.BooleanField(default=False, editable=False)
    motivo_sin_puntaje = models.CharField(
        max_length=255,
        blank=True,
        editable=False,
    )
    activo = models.BooleanField(default=True)

    # Código generado por el servidor: ACT-AAAA-000123.
    codigo = models.CharField(
        max_length=20,
        unique=True,
        null=True,
        blank=True,
        editable=False,
        verbose_name="Código",
    )
    rut_usuario = models.CharField(
        max_length=12,
        blank=True,
        db_index=True,
        validators=[validar_rut_opcional],
        verbose_name="RUT del usuario/a",
    )
    evidencia = models.FileField(
        upload_to=ruta_evidencia,
        blank=True,
        validators=[validar_evidencia],
        verbose_name="Evidencia (PDF, JPG o PNG)",
    )
    evidencia_nombre = models.CharField(max_length=255, blank=True, editable=False)

    # ---- Verificación ----
    estado_verificacion = models.CharField(
        max_length=12,
        choices=ESTADOS_VERIFICACION,
        default=PENDIENTE,
        editable=False,
        verbose_name="Estado de verificación",
    )
    verificado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        editable=False,
        related_name="actividades_verificadas",
        verbose_name="Verificado por",
    )
    fecha_verificacion = models.DateTimeField(null=True, blank=True, editable=False)
    observacion_verificacion = models.TextField(
        blank=True,
        max_length=500,
        editable=False,
        verbose_name="Observación de la verificación",
    )

    # ---- Tubo de seguimiento ----
    ingresa_tubo = models.BooleanField(
        default=False,
        verbose_name="Ingresa al tubo de seguimiento",
    )
    es_emergencia = models.BooleanField(default=False, verbose_name="Es emergencia")
    estado_tubo = models.CharField(
        max_length=12,
        choices=ESTADOS_TUBO,
        default=TUBO_EN_PROCESO,
        verbose_name="Estado en el tubo",
    )
    fecha_solucion = models.DateField(null=True, blank=True, editable=False)

    class Meta:
        ordering = ["-fecha_ingreso", "-id"]
        verbose_name = "Registro de actividad"
        verbose_name_plural = "Registros de actividades"
        permissions = [
            (
                "verificar_registroactividad",
                "Puede verificar actividades de su delegación",
            ),
        ]
        indexes = [
            models.Index(fields=["funcionario", "fecha_ingreso"], name="act_func_ingreso_idx"),
            models.Index(fields=["fecha_actividad", "activo"], name="act_fecha_activo_idx"),
            models.Index(
                fields=["estado_verificacion", "fecha_actividad"],
                name="act_verif_fecha_idx",
            ),
            models.Index(fields=["ingresa_tubo", "estado_tubo"], name="act_tubo_estado_idx"),
            models.Index(fields=["nombre_usuario"], name="act_nombre_usuario_idx"),
        ]

    def __str__(self):
        return f"{self.fecha_actividad} - {self.actividad} - {self.funcionario}"

    @property
    def esta_aprobado(self):
        return self.estado_verificacion == self.APROBADA

    @property
    def puede_modificarse(self):
        return self.activo and not self.esta_aprobado

    @property
    def cuenta_para_meta(self):
        """Solo los registros aprobados que puntúan ponderan a la meta."""
        return self.activo and self.puntua and self.esta_aprobado

    def tiene_datos_contacto(self):
        return bool(self.nombre_usuario.strip()) and len(normalizar_telefono(self.telefono_usuario)) == 9

    def es_gestion_del_delegado(self):
        if self.solicitante_tipo == self.TIPO_DELEGADO:
            return True

        if not self.funcionario_id:
            return False

        delegacion = self.funcionario.delegacion
        if not delegacion:
            return False

        if (
            nombre_comparable(self.nombre_usuario)
            and nombre_comparable(self.nombre_usuario) == nombre_comparable(delegacion.encargado)
        ):
            return True

        telefono = normalizar_telefono(self.telefono_usuario)
        telefonos_delegacion = (
            normalizar_telefono(delegacion.telefono),
            normalizar_telefono(delegacion.celular),
        )
        return bool(telefono and telefono in telefonos_delegacion)

    def actualizar_puntaje(self):
        """R1, R2 y R5: el puntaje se calcula, nunca se recibe del formulario."""
        if not self.activo:
            motivo = "Registro inactivo"
        elif self.es_gestion_del_delegado():
            motivo = "Otra gestión: el usuario es el delegado"
        elif not self.tiene_datos_contacto():
            motivo = "Sin nombre o teléfono válido del usuario"
        elif not self.actividad.puntua:
            motivo = "Gestión preparatoria: no suma puntaje"
        else:
            motivo = ""

        self.puntua = not bool(motivo)
        self.motivo_sin_puntaje = motivo

    def clean(self):
        super().clean()
        if self.rut_usuario:
            from seguridadAPP.models import normalizar_rut

            self.rut_usuario = normalizar_rut(self.rut_usuario)

        if not self.ingresa_tubo:
            self.es_emergencia = False
            self.estado_tubo = self.TUBO_EN_PROCESO

        if not self.fecha_actividad:
            return

        hoy = timezone.localdate(timezone.now(), timezone=ZONA_CHILE)
        if self.fecha_actividad > hoy:
            raise ValidationError({"fecha_actividad": "No puedes registrar actividades con fecha futura."})
        if hoy > fecha_cierre_semana(self.fecha_actividad):
            raise ValidationError({"fecha_actividad": "La semana de esta actividad ya está cerrada."})

    def save(self, *args, **kwargs):
        """Valida en el servidor y bloquea por funcionario para aplicar R3 sin carreras."""
        from seguridadAPP.models import PerfilUsuario

        with transaction.atomic():
            anterior = None
            if self.pk:
                anterior = type(self).objects.select_for_update().filter(pk=self.pk).first()
                if anterior:
                    if anterior.estado_verificacion == self.APROBADA:
                        raise ValidationError(MENSAJE_APROBADO)
                    if anterior.funcionario_id != self.funcionario_id:
                        raise ValidationError("No puedes cambiar el funcionario de un registro existente.")
                    if anterior.fecha_ingreso != self.fecha_ingreso:
                        raise ValidationError("La fecha de ingreso no se puede modificar.")
                    hoy = timezone.localdate(timezone.now(), timezone=ZONA_CHILE)
                    if hoy > fecha_cierre_semana(anterior.fecha_actividad):
                        raise ValidationError("Este registro ya no puede editarse: su semana está cerrada.")
            else:
                # La fecha de ingreso siempre la fija el servidor (R3).
                self.fecha_ingreso = timezone.now()

            # Bloqueo por funcionario para serializar ingresos simultáneos.
            PerfilUsuario.objects.select_for_update().get(pk=self.funcionario_id)
            self.full_clean()
            self.actualizar_puntaje()

            # Al crear o reactivar, contar los registros activos del día de ingreso.
            entra_al_cupo = self.activo and (anterior is None or not anterior.activo)
            if entra_al_cupo:
                fecha_local = timezone.localtime(self.fecha_ingreso, ZONA_CHILE).date()
                inicio, fin = rango_dia_chile(fecha_local)
                existentes = type(self).objects.filter(
                    funcionario_id=self.funcionario_id,
                    activo=True,
                    fecha_ingreso__gte=inicio,
                    fecha_ingreso__lt=fin,
                )
                if anterior is not None:
                    existentes = existentes.exclude(pk=self.pk)
                limite = getattr(settings, "MAX_INGRESOS_DIARIOS", 7)
                if existentes.count() >= limite:
                    raise ValidationError(
                        f"Ya registraste {limite} actividades ese día; el máximo diario es {limite}."
                    )

            self.actualizar_fecha_solucion()

            if kwargs.get("update_fields") is not None:
                kwargs["update_fields"] = set(kwargs["update_fields"]) | {
                    "puntua", "motivo_sin_puntaje"
                }
            resultado = super().save(*args, **kwargs)

            if not self.codigo:
                self.asignar_codigo()
            return resultado

    # ------------------------------------------------------------
    # Código automático
    # ------------------------------------------------------------

    def asignar_codigo(self):
        anio = timezone.localtime(self.fecha_ingreso, ZONA_CHILE).year
        self.codigo = f"ACT-{anio}-{self.pk:06d}"
        type(self).objects.filter(pk=self.pk).update(codigo=self.codigo)

    def actualizar_fecha_solucion(self):
        if self.ingresa_tubo and self.estado_tubo == self.TUBO_SOLUCIONADO:
            if self.fecha_solucion is None:
                self.fecha_solucion = timezone.localdate(timezone.now(), timezone=ZONA_CHILE)
        else:
            self.fecha_solucion = None

    # ------------------------------------------------------------
    # Verificación por el delegado
    # ------------------------------------------------------------

    def verificar(self, usuario, estado, observacion=""):
        """
        Aprueba, rechaza o pide antecedentes. No pasa por save(): el
        delegado verifica aunque la semana del registro ya esté cerrada
        (R4 limita el ingreso del funcionario, no la revisión).
        """
        observacion = (observacion or "").strip()
        estados_validos = {self.APROBADA, self.RECHAZADA, self.ANTECEDENTES}
        if estado not in estados_validos:
            raise ValidationError("El estado de verificación no es válido.")
        if estado != self.APROBADA and not observacion:
            raise ValidationError(
                "Indique el motivo del rechazo o los antecedentes que faltan."
            )
        if len(observacion) > 500:
            raise ValidationError("La observación no puede superar 500 caracteres.")

        with transaction.atomic():
            actual = type(self).objects.select_for_update().get(pk=self.pk)
            if not actual.activo:
                raise ValidationError("No se puede verificar un registro dado de baja.")
            if actual.estado_verificacion == self.APROBADA:
                raise ValidationError(MENSAJE_APROBADO)
            if actual.funcionario.usuario_id == usuario.pk:
                raise ValidationError("Nadie puede verificar sus propios registros.")

            ahora = timezone.now()
            type(self).objects.filter(pk=self.pk).update(
                estado_verificacion=estado,
                verificado_por=usuario,
                fecha_verificacion=ahora,
                observacion_verificacion=observacion,
            )

        self.estado_verificacion = estado
        self.verificado_por = usuario
        self.fecha_verificacion = ahora
        self.observacion_verificacion = observacion

    def cambiar_estado_tubo(self, estado):
        """
        Seguimiento del tubo por su dueño. Tampoco pasa por save(): el
        caso puede resolverse semanas después de su ingreso (R4 no aplica
        al seguimiento), pero un registro aprobado ya no cambia.
        """
        if estado not in dict(self.ESTADOS_TUBO):
            raise ValidationError("El estado del tubo no es válido.")

        with transaction.atomic():
            actual = type(self).objects.select_for_update().get(pk=self.pk)
            if not actual.ingresa_tubo or not actual.activo:
                raise ValidationError("El registro no está en el tubo de seguimiento.")
            if actual.estado_verificacion == self.APROBADA:
                raise ValidationError(MENSAJE_APROBADO)

            self.ingresa_tubo = True
            self.estado_tubo = estado
            self.fecha_solucion = actual.fecha_solucion
            self.actualizar_fecha_solucion()
            type(self).objects.filter(pk=self.pk).update(
                estado_tubo=self.estado_tubo,
                fecha_solucion=self.fecha_solucion,
            )
