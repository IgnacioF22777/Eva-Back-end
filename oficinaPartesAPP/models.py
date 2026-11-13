import re
from datetime import date

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxLengthValidator
from django.db import models

from delegacionesAPP.models import Delegacion


MAX_TEMA = 1000
MAX_OBSERVACION = 1000

# Una carta en proceso por más de estos días se marca como atrasada.
DIAS_ALERTA = 15


def validar_telefono(valor):
    """Acepta formatos chilenos: «9 5317 1972», «+56 9 1234 5678», «512200000»."""
    digitos = re.sub(r"\D", "", valor or "")
    if valor and (re.search(r"[^\d\s+()-]", valor) or not 8 <= len(digitos) <= 12):
        raise ValidationError(
            "Ingrese un teléfono válido (8 a 12 dígitos; se permiten espacios, + y guiones)."
        )


# ============================================================
# TUBO DE CARTAS DE OFICINA DE PARTES
# ============================================================
# Seguimiento de las cartas que llegan a la delegación por Oficina de
# Partes (dirigidas a la Alcaldesa, al Delegado u otra autoridad): quién
# las envía, qué piden, quién hace el seguimiento y en qué estado están.

class CartaOficinaPartes(models.Model):

    ALCALDESA = "ALCALDESA"
    DELEGADO = "DELEGADO"
    OTRO = "OTRO"
    DESTINATARIOS = [
        (ALCALDESA, "Alcaldesa"),
        (DELEGADO, "Delegado"),
        (OTRO, "Otro"),
    ]

    EN_PROCESO = "EN_PROCESO"
    APROBADA = "APROBADA"
    FINALIZADA = "FINALIZADA"
    NO_APLICA = "NO_APLICA"
    ESTADOS = [
        (EN_PROCESO, "En proceso"),
        (APROBADA, "Aprobada"),
        (FINALIZADA, "Finalizada"),
        (NO_APLICA, "No aplica"),
    ]
    ESTADOS_CERRADOS = (FINALIZADA, NO_APLICA)

    PRONUNCIAMIENTOS = [
        ("", "Pendiente"),
        ("ALCALDESA", "Alcaldesa"),
        ("GABINETE", "Gabinete"),
        ("DELEGADO", "Delegado"),
        ("NO_APLICA", "No aplica"),
    ]

    delegacion = models.ForeignKey(
        Delegacion,
        on_delete=models.PROTECT,
        related_name="cartas",
        verbose_name="Delegación",
    )

    fecha_recepcion = models.DateField(
        default=date.today,
        verbose_name="Fecha de recepción",
    )

    numero_ingreso = models.CharField(
        max_length=20,
        blank=True,
        verbose_name="N° de ingreso de Oficina de Partes",
    )

    destinatario = models.CharField(
        max_length=10,
        choices=DESTINATARIOS,
        default=ALCALDESA,
        verbose_name="Dirigida a",
    )

    remitente = models.CharField(
        max_length=150,
        verbose_name="Remitente",
        help_text="Persona u organización que envía la carta.",
    )

    telefono_contacto = models.CharField(
        max_length=20,
        blank=True,
        validators=[validar_telefono],
        verbose_name="Teléfono de contacto",
    )

    tema = models.TextField(
        max_length=MAX_TEMA,
        validators=[MaxLengthValidator(MAX_TEMA)],
        verbose_name="Actividad o tema",
    )

    fecha_actividad = models.CharField(
        max_length=60,
        blank=True,
        verbose_name="Fecha de la actividad",
        help_text="Fecha o período solicitado (ej.: «16 al 19/07»).",
    )

    encargado_seguimiento = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="Encargado del seguimiento",
        help_text="Unidad o persona responsable (ej.: Patrocinios, Fomento).",
    )

    estado = models.CharField(
        max_length=12,
        choices=ESTADOS,
        default=EN_PROCESO,
        db_index=True,
        verbose_name="Estado",
    )

    pronunciamiento = models.CharField(
        max_length=10,
        choices=PRONUNCIAMIENTOS,
        blank=True,
        verbose_name="Pronunciamiento",
    )

    derivada_a = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="Derivada a",
    )

    observacion = models.TextField(
        blank=True,
        max_length=MAX_OBSERVACION,
        validators=[MaxLengthValidator(MAX_OBSERVACION)],
        verbose_name="Observación",
    )

    fecha_cierre = models.DateField(
        null=True,
        blank=True,
        editable=False,
        verbose_name="Fecha de cierre",
    )

    registrada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        editable=False,
        related_name="cartas_registradas",
        verbose_name="Registrada por",
    )

    # Baja lógica: una carta ingresada por error se anula, no se borra.
    activo = models.BooleanField(default=True, verbose_name="Vigente")

    class Meta:
        verbose_name = "Carta de Oficina de Partes"
        verbose_name_plural = "Cartas de Oficina de Partes"
        ordering = ["-fecha_recepcion", "-pk"]
        indexes = [
            models.Index(fields=["delegacion", "estado"], name="carta_delegacion_estado_idx"),
        ]

    def __str__(self):
        numero = f"N° {self.numero_ingreso} · " if self.numero_ingreso else ""
        return f"{numero}{self.remitente}"

    @property
    def cerrada(self):
        return self.estado in self.ESTADOS_CERRADOS

    @property
    def dias_abierta(self):
        if not self.fecha_recepcion:
            return 0
        hasta = self.fecha_cierre if self.cerrada and self.fecha_cierre else date.today()
        return max((hasta - self.fecha_recepcion).days, 0)

    @property
    def atrasada(self):
        return self.estado == self.EN_PROCESO and self.dias_abierta > DIAS_ALERTA

    def clean(self):
        super().clean()

        self.remitente = " ".join((self.remitente or "").split())
        self.numero_ingreso = " ".join((self.numero_ingreso or "").split())

        if not self.remitente:
            raise ValidationError({"remitente": "El remitente es obligatorio."})

        if not (self.tema or "").strip():
            raise ValidationError({"tema": "Indique la actividad o el tema de la carta."})

        if self.fecha_recepcion and self.fecha_recepcion > date.today():
            raise ValidationError({"fecha_recepcion": "La fecha de recepción no puede ser futura."})

    def save(self, *args, **kwargs):
        # La fecha de cierre se fija al pasar a Finalizada o No aplica y se
        # borra si la carta se reabre.
        if self.cerrada and self.fecha_cierre is None:
            self.fecha_cierre = date.today()
        elif not self.cerrada:
            self.fecha_cierre = None

        update_fields = kwargs.get("update_fields")
        if update_fields is not None:
            kwargs["update_fields"] = set(update_fields) | {"fecha_cierre"}

        super().save(*args, **kwargs)
