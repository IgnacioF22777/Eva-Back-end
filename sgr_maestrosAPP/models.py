
from decimal import Decimal

from django.db import models
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, MaxValueValidator


# ============================================================
# MODELO 1: CATÁLOGO DE ACTIVIDADES
# ============================================================

class CatalogoActividad(models.Model):

    codigo = models.CharField(
        max_length=40,
        unique=True
    )

    nombre = models.CharField(
        max_length=150
    )

    descripcion = models.TextField(
        blank=True
    )

    area = models.CharField(
        max_length=100,
        blank=True
    )

    activo = models.BooleanField(
        default=True
    )

    class Meta:
        verbose_name = "Actividad del catálogo"
        verbose_name_plural = "Catálogo de actividades"
        ordering = ["nombre"]

    def __str__(self):
        return f"{self.codigo} - {self.nombre}"

    def clean(self):
        super().clean()

        self.codigo = (self.codigo or "").strip().upper()
        self.nombre = (self.nombre or "").strip()

        if not self.codigo:
            raise ValidationError({
                "codigo": "El código es obligatorio."
            })

        if not self.nombre:
            raise ValidationError({
                "nombre": "El nombre es obligatorio."
            })

        if CatalogoActividad.objects.exclude(
            pk=self.pk
        ).filter(
            codigo__iexact=self.codigo
        ).exists():
            raise ValidationError({
                "codigo": "Ya existe una actividad con este código."
            })


# ============================================================
# MODELO 2: GESTIÓN DE PERÍODOS
# ============================================================

class Periodo(models.Model):

    codigo = models.CharField(
        max_length=30,
        unique=True,
        verbose_name="Código"
    )

    nombre = models.CharField(
        max_length=150,
        verbose_name="Nombre del período"
    )

    fecha_inicio = models.DateField(
        verbose_name="Fecha de inicio"
    )

    fecha_fin = models.DateField(
        verbose_name="Fecha de término"
    )

    cerrado = models.BooleanField(
        default=False,
        verbose_name="Período cerrado"
    )

    class Meta:
        verbose_name = "Período"
        verbose_name_plural = "Períodos"
        ordering = ["-fecha_inicio"]

    def __str__(self):
        return f"{self.codigo} - {self.nombre}"

    def clean(self):
        super().clean()

        if (
            self.fecha_inicio
            and self.fecha_fin
            and self.fecha_fin < self.fecha_inicio
        ):
            raise ValidationError({
                "fecha_fin": (
                    "La fecha de término no puede ser "
                    "anterior a la fecha de inicio."
                )
            })


# ============================================================
# MODELO 3: DETALLE DE PERÍODO
# ============================================================

class DetallePeriodo(models.Model):

    periodo = models.ForeignKey(
        Periodo,
        on_delete=models.PROTECT,
        related_name="detalles",
        verbose_name="Período"
    )

    nombre = models.CharField(
        max_length=150,
        verbose_name="Nombre del detalle"
    )

    fecha_inicio = models.DateField(
        verbose_name="Fecha de inicio"
    )

    fecha_fin = models.DateField(
        verbose_name="Fecha de término"
    )

    dias_computables = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name="Días computables",
        help_text=(
            "Valor provisional. El cálculo automático "
            "debe considerar fines de semana y feriados."
        )
    )

    observaciones = models.TextField(
        blank=True,
        verbose_name="Observaciones"
    )

    # Baja logica: el detalle se conserva para no perder trazabilidad.
    activo = models.BooleanField(
        default=True,
        verbose_name="Activo"
    )

    class Meta:
        verbose_name = "Detalle de período"
        verbose_name_plural = "Detalles de períodos"
        ordering = ["fecha_inicio"]

        constraints = [
            models.UniqueConstraint(
                fields=["periodo", "nombre"],
                name="unique_detalle_nombre_periodo"
            )
        ]

    def __str__(self):
        return f"{self.periodo.codigo} - {self.nombre}"

    def clean(self):
        super().clean()

        if (
            self.fecha_inicio
            and self.fecha_fin
            and self.fecha_fin < self.fecha_inicio
        ):
            raise ValidationError({
                "fecha_fin": (
                    "La fecha de término no puede ser "
                    "anterior a la fecha de inicio."
                )
            })

        if self.periodo_id:
            periodo = self.periodo

            if (
                self.fecha_inicio
                and self.fecha_inicio < periodo.fecha_inicio
            ):
                raise ValidationError({
                    "fecha_inicio": (
                        "El detalle no puede comenzar "
                        "antes del período principal."
                    )
                })

            if (
                self.fecha_fin
                and self.fecha_fin > periodo.fecha_fin
            ):
                raise ValidationError({
                    "fecha_fin": (
                        "El detalle no puede terminar "
                        "después del período principal."
                    )
                })


# ============================================================
# MODELO 4: GESTIÓN DE METAS
# ============================================================

class Meta(models.Model):

    codigo = models.CharField(
        max_length=40,
        unique=True,
        verbose_name="Código de la meta"
    )

    nombre = models.CharField(
        max_length=150,
        verbose_name="Nombre de la meta"
    )

    descripcion = models.TextField(
        blank=True,
        verbose_name="Descripción"
    )

    periodo = models.ForeignKey(
        Periodo,
        on_delete=models.PROTECT,
        related_name="metas",
        verbose_name="Período de evaluación"
    )

    actividad = models.ForeignKey(
        CatalogoActividad,
        on_delete=models.PROTECT,
        related_name="metas",
        verbose_name="Actividad del catálogo"
    )

    valor_objetivo = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[
            MinValueValidator(Decimal("0.01"))
        ],
        verbose_name="Valor objetivo",
        help_text="Cantidad que se espera alcanzar."
    )

    ponderacion = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        validators=[
            MinValueValidator(Decimal("0.00")),
            MaxValueValidator(Decimal("100.00"))
        ],
        verbose_name="Ponderación (%)",
        help_text="Peso porcentual de la meta."
    )

    activo = models.BooleanField(
        default=True,
        verbose_name="Meta activa"
    )

    class Meta:
        verbose_name = "Meta"
        verbose_name_plural = "Metas"
        ordering = ["nombre"]

    def __str__(self):
        return f"{self.codigo} - {self.nombre}"

    def clean(self):
        super().clean()

        self.codigo = (self.codigo or "").strip().upper()
        self.nombre = (self.nombre or "").strip()

        errores = {}

        if not self.codigo:
            errores["codigo"] = "El código es obligatorio."

        if not self.nombre:
            errores["nombre"] = "El nombre es obligatorio."

        if self.codigo and Meta.objects.exclude(
            pk=self.pk
        ).filter(
            codigo__iexact=self.codigo
        ).exists():
            errores["codigo"] = (
                "Ya existe una meta con este código."
            )

        if (
            self.valor_objetivo is not None
            and self.valor_objetivo <= 0
        ):
            errores["valor_objetivo"] = (
                "El valor objetivo debe ser mayor que cero."
            )

        if self.ponderacion is not None:
            if (
                self.ponderacion < 0
                or self.ponderacion > 100
            ):
                errores["ponderacion"] = (
                    "La ponderación debe estar entre 0 y 100."
                )

        if errores:
            raise ValidationError(errores)
