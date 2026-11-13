from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxLengthValidator
from django.db import models
from django.utils import timezone

from delegacionesAPP.models import Delegacion
from oficinaPartesAPP.models import validar_telefono


MAX_DETALLE = 1000


# ============================================================
# TIPOS Y SUBTIPOS DE ATENCIÓN SOCIAL (hojas LISTA y DATO MENU)
# ============================================================
INFORME = "INFORME"
SUBSIDIO = "SUBSIDIO"
DERIVACION = "DERIVACION"
OTRA = "OTRA"

TIPOS = [
    (INFORME, "Informe social"),
    (SUBSIDIO, "Gestión de subsidio"),
    (DERIVACION, "Derivación"),
    (OTRA, "Otra gestión social"),
]

SUBTIPOS = [
    ("APORTE_ECONOMICO", "Aporte económico"),
    ("APORTE_MATERIAL", "Aporte material"),
    ("INSTITUCION", "Institución"),
    ("IPS", "IPS"),
    ("PGU", "PGU (Pensión Garantizada Universal)"),
    ("SUF", "SUF (Subsidio Único Familiar)"),
    ("SAP", "SAP (Subsidio de Agua Potable)"),
]

# Subtipos válidos para cada tipo. Un tipo sin subtipos no admite subtipo.
SUBTIPOS_POR_TIPO = {
    INFORME: {"APORTE_ECONOMICO", "APORTE_MATERIAL", "INSTITUCION"},
    SUBSIDIO: {"IPS", "PGU", "SUF", "SAP"},
    DERIVACION: set(),
    OTRA: set(),
}


def validar_tipo_subtipo(tipo, subtipo):
    """Regla de HU-34: el subtipo debe ser coherente con el tipo."""
    if tipo not in SUBTIPOS_POR_TIPO:
        raise ValidationError({"tipo": "Seleccione un tipo de atención válido."})

    validos = SUBTIPOS_POR_TIPO[tipo]
    if validos and not subtipo:
        raise ValidationError({"subtipo": "Este tipo de atención requiere un subtipo."})
    if subtipo and subtipo not in validos:
        etiqueta = dict(TIPOS)[tipo]
        raise ValidationError({"subtipo": f"El subtipo no corresponde a «{etiqueta}»."})


class AtencionSocial(models.Model):
    delegacion = models.ForeignKey(
        Delegacion,
        on_delete=models.PROTECT,
        related_name="atenciones_sociales",
        verbose_name="Delegación",
    )
    fecha = models.DateField(default=timezone.localdate, verbose_name="Fecha de la atención")
    tipo = models.CharField(max_length=12, choices=TIPOS, verbose_name="Tipo de atención")
    subtipo = models.CharField(
        max_length=20,
        choices=SUBTIPOS,
        blank=True,
        verbose_name="Subtipo",
        help_text="Informe: aporte económico, material o institución. Subsidio: IPS, PGU, SUF o SAP.",
    )
    nombre_vecino = models.CharField(max_length=150, verbose_name="Nombre del vecino/a")
    telefono_vecino = models.CharField(
        max_length=20,
        blank=True,
        validators=[validar_telefono],
        verbose_name="Teléfono del vecino/a",
    )
    derivada_a = models.CharField(
        max_length=150,
        blank=True,
        verbose_name="Derivada a",
        help_text="Obligatorio en derivaciones: institución o unidad de destino.",
    )
    detalle = models.TextField(
        blank=True,
        max_length=MAX_DETALLE,
        validators=[MaxLengthValidator(MAX_DETALLE)],
        verbose_name="Detalle",
    )
    registrada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="atenciones_sociales",
        null=True,
        editable=False,
    )
    creada = models.DateTimeField(auto_now_add=True)
    activo = models.BooleanField(default=True)

    class Meta:
        ordering = ["-fecha", "-id"]
        verbose_name = "Atención social"
        verbose_name_plural = "Atenciones sociales"
        indexes = [
            models.Index(fields=["delegacion", "fecha"], name="ats_deleg_fecha_idx"),
            models.Index(fields=["tipo", "subtipo"], name="ats_tipo_subtipo_idx"),
        ]

    def __str__(self):
        return f"{self.fecha} - {self.get_tipo_display()} - {self.nombre_vecino}"

    def clean(self):
        super().clean()
        self.nombre_vecino = (self.nombre_vecino or "").strip()
        self.derivada_a = (self.derivada_a or "").strip()

        validar_tipo_subtipo(self.tipo, self.subtipo)

        if self.tipo == DERIVACION and not self.derivada_a:
            raise ValidationError({"derivada_a": "Indique a qué institución o unidad se derivó."})
        if self.fecha and self.fecha > timezone.localdate():
            raise ValidationError({"fecha": "La atención no puede tener fecha futura."})
