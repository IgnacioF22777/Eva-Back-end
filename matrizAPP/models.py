import os
import uuid

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.core.validators import MaxLengthValidator, MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone

from sgr_maestrosAPP.feriados import feriados_entre
from tubo_gestionAPP.adjuntos import extension_de, validar_archivo_adjunto
from tubo_gestionAPP.validadores import calcular_dias_computables

from .reglas import BONO_FELICITACION, DESCUENTO_RECLAMO, se_traslapan


MAX_TEXTO = 1000


def delegacion_del_funcionario(usuario):
    """Delegación del perfil del funcionario, o None si no tiene."""
    try:
        return usuario.perfil.delegacion
    except (AttributeError, ObjectDoesNotExist):
        return None


def ruta_respaldo(instancia, nombre):
    """
    Nombre aleatorio en el servidor, igual que los adjuntos de avances:
    el nombre que escribe el usuario nunca forma parte de la ruta.
    """
    extension = extension_de(nombre)
    sufijo = f".{extension}" if extension else ""
    return f"respaldos_matriz/{uuid.uuid4().hex}{sufijo}"


# ============================================================
# MODELO 1: AUSENCIA (R9)
# ============================================================
# "Los días libres, de vacaciones, días administrativos y licencias
# deben ser ingresados por el delegado en la pestaña de semáforo para el
# ajuste de las metas." La ausencia descuenta días hábiles del período y
# así baja la meta del funcionario en proporción.

class Ausencia(models.Model):

    TIPOS = [
        ("DIA_LIBRE", "Día libre"),
        ("VACACIONES", "Vacaciones"),
        ("ADMINISTRATIVO", "Día administrativo"),
        ("LICENCIA", "Licencia médica"),
        ("COMPENSATORIO", "Compensatorio"),
        ("EMERGENCIA", "Emergencia"),
    ]

    funcionario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="ausencias",
        verbose_name="Funcionario",
    )

    # Se copia del perfil al registrar: si el funcionario cambia de
    # delegación, la ausencia sigue perteneciendo a la que la registró.
    delegacion = models.ForeignKey(
        "delegacionesAPP.Delegacion",
        on_delete=models.PROTECT,
        related_name="ausencias",
        editable=False,
        verbose_name="Delegación",
    )

    tipo = models.CharField(
        max_length=20,
        choices=TIPOS,
        verbose_name="Tipo de ausencia",
    )

    fecha_inicio = models.DateField(verbose_name="Desde")
    fecha_fin = models.DateField(verbose_name="Hasta")

    dias = models.PositiveIntegerField(
        default=0,
        editable=False,
        verbose_name="Días hábiles",
        help_text="Se calcula solo: sin fines de semana ni feriados.",
    )

    observacion = models.TextField(
        blank=True,
        max_length=MAX_TEXTO,
        validators=[MaxLengthValidator(MAX_TEXTO)],
        verbose_name="Observación",
    )

    registrado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="ausencias_registradas",
        editable=False,
        verbose_name="Registrada por",
    )

    fecha_registro = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Fecha de registro",
    )

    # Baja lógica: una ausencia anulada se conserva como historial.
    activo = models.BooleanField(default=True, verbose_name="Vigente")

    class Meta:
        verbose_name = "Ausencia"
        verbose_name_plural = "Ausencias"
        ordering = ["-fecha_inicio", "-pk"]
        indexes = [
            models.Index(
                fields=["funcionario", "activo", "fecha_inicio"],
                name="ausencia_func_activo_idx",
            ),
        ]

    def __str__(self):
        return (
            f"{self.get_tipo_display()} de {self.funcionario.get_full_name()} "
            f"({self.fecha_inicio:%d-%m-%Y} a {self.fecha_fin:%d-%m-%Y})"
        )

    def calcular_dias(self):
        if not (self.fecha_inicio and self.fecha_fin) or self.fecha_fin < self.fecha_inicio:
            return 0

        return calcular_dias_computables(
            self.fecha_inicio,
            self.fecha_fin,
            feriados_entre(self.fecha_inicio, self.fecha_fin),
        )

    def clean(self):
        super().clean()

        if self.fecha_inicio and self.fecha_fin:
            if self.fecha_fin < self.fecha_inicio:
                raise ValidationError({
                    "fecha_fin": "La fecha de término no puede ser anterior al inicio."
                })

            if self.calcular_dias() == 0:
                raise ValidationError({
                    "fecha_fin": (
                        "El rango no tiene días hábiles (solo fines de semana "
                        "o feriados): no afecta la meta."
                    )
                })

        if self.funcionario_id:
            if self.delegacion_id is None:
                delegacion = delegacion_del_funcionario(self.funcionario)
                if delegacion is None:
                    raise ValidationError({
                        "funcionario": "El funcionario no tiene delegación asignada."
                    })
                self.delegacion = delegacion

            # Solo se revisa el traslape de ausencias vigentes.
            if self.activo and self.fecha_inicio and self.fecha_fin:
                otras = Ausencia.objects.filter(
                    funcionario_id=self.funcionario_id, activo=True,
                ).exclude(pk=self.pk)

                for otra in otras:
                    if se_traslapan(self.fecha_inicio, self.fecha_fin,
                                    otra.fecha_inicio, otra.fecha_fin):
                        raise ValidationError({
                            "fecha_inicio": (
                                "Se cruza con otra ausencia vigente del "
                                f"funcionario: {otra.get_tipo_display()} del "
                                f"{otra.fecha_inicio:%d-%m-%Y} al "
                                f"{otra.fecha_fin:%d-%m-%Y}."
                            )
                        })

    def save(self, *args, **kwargs):
        # Los días nunca se escriben a mano: siempre salen del rango.
        self.dias = self.calcular_dias()

        if self.delegacion_id is None and self.funcionario_id:
            self.delegacion = delegacion_del_funcionario(self.funcionario)

        update_fields = kwargs.get("update_fields")
        if update_fields is not None:
            kwargs["update_fields"] = set(update_fields) | {"dias"}

        super().save(*args, **kwargs)


# ============================================================
# MODELO 2: FELICITACIONES Y RECLAMOS (R8 y hoja RECLAMOS)
# ============================================================
# Felicitación: +10% al cumplimiento. Solo vale con respaldo formal
# dirigido al delegado o a la delegación, y la registra el delegado,
# nunca el funcionario felicitado.
# Reclamo: -20% al cumplimiento. Solo por escrito y por mala atención.

class AjusteDesempeno(models.Model):

    FELICITACION = "FELICITACION"
    RECLAMO = "RECLAMO"

    TIPOS = [
        (FELICITACION, "Felicitación (+10%)"),
        (RECLAMO, "Reclamo (−20%)"),
    ]

    # No existe la opción "mensaje al funcionario": según R8, una
    # felicitación enviada directo al gestor no es válida.
    MEDIOS = [
        ("CORREO_DELEGADO", "Correo al delegado"),
        ("WHATSAPP_DELEGADO", "WhatsApp al delegado"),
        ("LIBRO_OBSERVACIONES", "Libro de observaciones de la oficina"),
        ("CARTA_DELEGACION", "Carta a la delegación"),
    ]

    tipo = models.CharField(max_length=15, choices=TIPOS, verbose_name="Tipo")

    funcionario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="ajustes_desempeno",
        verbose_name="Funcionario",
    )

    delegacion = models.ForeignKey(
        "delegacionesAPP.Delegacion",
        on_delete=models.PROTECT,
        related_name="ajustes_desempeno",
        editable=False,
        verbose_name="Delegación",
    )

    fecha = models.DateField(verbose_name="Fecha de recepción")

    medio = models.CharField(
        max_length=25,
        choices=MEDIOS,
        verbose_name="Medio escrito",
    )

    remitente_nombre = models.CharField(
        max_length=150,
        verbose_name="Nombre de quien felicita o reclama",
    )

    remitente_contacto = models.CharField(
        max_length=100,
        verbose_name="Contacto (teléfono o correo)",
    )

    descripcion = models.TextField(
        max_length=MAX_TEXTO,
        validators=[MaxLengthValidator(MAX_TEXTO)],
        verbose_name="Descripción",
    )

    respaldo = models.FileField(
        upload_to=ruta_respaldo,
        max_length=255,
        validators=[validar_archivo_adjunto],
        verbose_name="Respaldo (captura, correo, foto del libro, carta)",
    )

    nombre_original = models.CharField(
        max_length=255,
        editable=False,
        verbose_name="Nombre del archivo",
    )

    registrado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="ajustes_registrados",
        editable=False,
        verbose_name="Registrado por",
    )

    fecha_registro = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Fecha de registro",
    )

    activo = models.BooleanField(default=True, verbose_name="Vigente")

    class Meta:
        verbose_name = "Felicitación o reclamo"
        verbose_name_plural = "Felicitaciones y reclamos"
        ordering = ["-fecha", "-pk"]
        indexes = [
            models.Index(
                fields=["funcionario", "tipo", "activo", "fecha"],
                name="ajuste_func_tipo_idx",
            ),
        ]

    def __str__(self):
        return f"{self.get_tipo_display()} - {self.funcionario.get_full_name()} ({self.fecha:%d-%m-%Y})"

    @property
    def es_felicitacion(self):
        return self.tipo == self.FELICITACION

    def clean(self):
        super().clean()

        self.remitente_nombre = (self.remitente_nombre or "").strip()
        self.remitente_contacto = (self.remitente_contacto or "").strip()
        self.descripcion = (self.descripcion or "").strip()

        errores = {}

        if not self.remitente_nombre:
            errores["remitente_nombre"] = "Indique quién envía la felicitación o el reclamo."

        if not self.remitente_contacto:
            errores["remitente_contacto"] = "Indique un teléfono o correo de contacto."

        if not self.descripcion:
            errores["descripcion"] = "Describa la felicitación o el reclamo."

        if self.fecha and self.fecha > timezone.localdate():
            errores["fecha"] = "La fecha no puede ser futura."

        if self.funcionario_id and self.delegacion_id is None:
            delegacion = delegacion_del_funcionario(self.funcionario)
            if delegacion is None:
                errores["funcionario"] = "El funcionario no tiene delegación asignada."
            else:
                self.delegacion = delegacion

        if errores:
            raise ValidationError(errores)

    def save(self, *args, **kwargs):
        # Archivo recién subido (todavía con su nombre original): se guarda
        # ese nombre para la descarga, antes de que se renombre al azar.
        if self.respaldo and not getattr(self.respaldo, "_committed", True):
            self.nombre_original = os.path.basename(self.respaldo.name)[:255]

        if self.delegacion_id is None and self.funcionario_id:
            self.delegacion = delegacion_del_funcionario(self.funcionario)

        super().save(*args, **kwargs)


# ============================================================
# CONFIGURACIÓN DE FELICITACIONES Y RECLAMOS (R8)
# ============================================================
# El profesor pidió que el descuento por reclamo se pueda elegir entre
# 20% y 30%, y que exista la opción de limitar (o no) las felicitaciones
# al tope de 120%. Es una sola fila (pk=1) que edita el Administrador;
# los valores de settings.py solo son el punto de partida.

DESCUENTO_MINIMO = 20
DESCUENTO_MAXIMO = 30


def porcentaje_entero(fraccion):
    return int((fraccion * 100).to_integral_value())


class ConfiguracionMatriz(models.Model):
    descuento_reclamo_pct = models.PositiveSmallIntegerField(
        "Descuento por reclamo (%)",
        default=porcentaje_entero(DESCUENTO_RECLAMO),
        validators=[
            MinValueValidator(DESCUENTO_MINIMO),
            MaxValueValidator(DESCUENTO_MAXIMO),
        ],
        help_text="Entre 20% y 30%, según la hoja RECLAMOS de la matriz.",
    )
    bono_felicitacion_pct = models.PositiveSmallIntegerField(
        "Bono por felicitación (%)",
        default=porcentaje_entero(BONO_FELICITACION),
        validators=[MinValueValidator(0), MaxValueValidator(50)],
        help_text="Porcentaje que suma cada felicitación (por defecto 10%).",
    )
    limitar_felicitaciones_al_tope = models.BooleanField(
        "Limitar las felicitaciones al tope de 120%",
        default=True,
        help_text=(
            "Si se desmarca, las felicitaciones se suman por encima del "
            "tope (ej.: 120% + una felicitación = 130%)."
        ),
    )
    actualizado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        editable=False,
        related_name="+",
    )
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Configuración de la matriz"
        verbose_name_plural = "Configuración de la matriz"

    def __str__(self):
        return (
            f"Reclamo -{self.descuento_reclamo_pct}%, "
            f"felicitación +{self.bono_felicitacion_pct}%"
        )

    def save(self, *args, **kwargs):
        # Siempre una sola configuración.
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def obtener(cls):
        config, _ = cls.objects.get_or_create(pk=1)
        return config

    @property
    def descuento(self):
        from decimal import Decimal
        return Decimal(self.descuento_reclamo_pct) / 100

    @property
    def bono(self):
        from decimal import Decimal
        return Decimal(self.bono_felicitacion_pct) / 100
