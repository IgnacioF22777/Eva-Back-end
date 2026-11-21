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


# Las listas anteriores son los valores iniciales: la migración 0002 los
# carga en las tablas TipoAtencion y SubtipoAtencion, que desde la Eva 3 se
# administran desde su propio mantenedor (pauta: CRUD de tipos y subtipos).


class TipoAtencion(models.Model):
    codigo = models.CharField(
        max_length=12,
        unique=True,
        verbose_name="Código",
        help_text="Identificador interno en mayúsculas. No se cambia una vez creado.",
    )
    nombre = models.CharField(max_length=100, verbose_name="Nombre del tipo")
    exige_destino = models.BooleanField(
        default=False,
        verbose_name="Exige indicar el destino",
        help_text="Marque para tipos como «Derivación»: obliga a indicar la institución o unidad de destino.",
    )
    activo = models.BooleanField(default=True, verbose_name="Vigente")

    class Meta:
        ordering = ["nombre"]
        verbose_name = "Tipo de atención social"
        verbose_name_plural = "Tipos de atención social"

    def __str__(self):
        return self.nombre

    def clean(self):
        super().clean()
        self.codigo = "_".join((self.codigo or "").upper().split())
        self.nombre = " ".join((self.nombre or "").split())
        if not self.codigo:
            raise ValidationError({"codigo": "El código es obligatorio."})
        if not self.nombre:
            raise ValidationError({"nombre": "El nombre es obligatorio."})


class SubtipoAtencion(models.Model):
    tipo = models.ForeignKey(
        TipoAtencion,
        on_delete=models.PROTECT,
        related_name="subtipos",
        verbose_name="Tipo de atención",
    )
    codigo = models.CharField(
        max_length=20,
        unique=True,
        verbose_name="Código",
        help_text="Identificador interno en mayúsculas. No se cambia una vez creado.",
    )
    nombre = models.CharField(max_length=100, verbose_name="Nombre del subtipo")
    activo = models.BooleanField(default=True, verbose_name="Vigente")

    class Meta:
        ordering = ["tipo__nombre", "nombre"]
        verbose_name = "Subtipo de atención social"
        verbose_name_plural = "Subtipos de atención social"

    def __str__(self):
        return f"{self.tipo.nombre} / {self.nombre}"

    def clean(self):
        super().clean()
        self.codigo = "_".join((self.codigo or "").upper().split())
        self.nombre = " ".join((self.nombre or "").split())
        if not self.codigo:
            raise ValidationError({"codigo": "El código es obligatorio."})
        if not self.nombre:
            raise ValidationError({"nombre": "El nombre es obligatorio."})


def nombre_tipo(codigo):
    tipo = TipoAtencion.objects.filter(codigo=codigo).values_list("nombre", flat=True).first()
    return tipo or dict(TIPOS).get(codigo, codigo)


def nombre_subtipo(codigo):
    if not codigo:
        return ""
    subtipo = SubtipoAtencion.objects.filter(codigo=codigo).values_list("nombre", flat=True).first()
    return subtipo or dict(SUBTIPOS).get(codigo, codigo)


def validar_tipo_subtipo(tipo, subtipo, tipo_anterior=None, subtipo_anterior=None):
    """
    Regla de HU-34: el subtipo debe ser coherente con el tipo.

    Los tipos y subtipos se leen de su mantenedor. Uno dado de baja ya no
    se ofrece para registros nuevos, pero un registro antiguo que lo usa
    puede seguir editándose sin cambiarlo.
    """
    tipo_obj = TipoAtencion.objects.filter(codigo=tipo).first()
    if tipo_obj is None or (not tipo_obj.activo and tipo != tipo_anterior):
        raise ValidationError({"tipo": "Seleccione un tipo de atención válido."})

    validos = set(tipo_obj.subtipos.filter(activo=True).values_list("codigo", flat=True))
    if subtipo and subtipo == subtipo_anterior and tipo == tipo_anterior:
        validos.add(subtipo)

    if validos and not subtipo:
        raise ValidationError({"subtipo": "Este tipo de atención requiere un subtipo."})
    if subtipo and subtipo not in validos:
        raise ValidationError({"subtipo": f"El subtipo no corresponde a «{tipo_obj.nombre}»."})


class AtencionSocial(models.Model):
    delegacion = models.ForeignKey(
        Delegacion,
        on_delete=models.PROTECT,
        related_name="atenciones_sociales",
        verbose_name="Delegación",
    )
    fecha = models.DateField(default=timezone.localdate, verbose_name="Fecha de la atención")
    # Guardan el código del tipo y del subtipo de su mantenedor
    # (TipoAtencion / SubtipoAtencion).
    tipo = models.CharField(max_length=12, verbose_name="Tipo de atención")
    subtipo = models.CharField(
        max_length=20,
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

    # Antes los entregaba Django desde las listas fijas (choices); ahora
    # el nombre viene del mantenedor.
    def get_tipo_display(self):
        return nombre_tipo(self.tipo)

    def get_subtipo_display(self):
        return nombre_subtipo(self.subtipo)

    def clean(self):
        super().clean()
        self.nombre_vecino = (self.nombre_vecino or "").strip()
        self.derivada_a = (self.derivada_a or "").strip()

        anterior = (
            AtencionSocial.objects.filter(pk=self.pk).values_list("tipo", "subtipo").first()
            if self.pk else None
        ) or (None, None)
        validar_tipo_subtipo(self.tipo, self.subtipo, *anterior)

        exige_destino = TipoAtencion.objects.filter(codigo=self.tipo, exige_destino=True).exists()
        if exige_destino and not self.derivada_a:
            raise ValidationError({"derivada_a": "Indique a qué institución o unidad se derivó."})
        if self.fecha and self.fecha > timezone.localdate():
            raise ValidationError({"fecha": "La atención no puede tener fecha futura."})
