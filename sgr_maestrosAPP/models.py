
from decimal import Decimal

from django.db import models
from django.core.exceptions import ValidationError
from django.core.validators import (
    MaxLengthValidator,
    MaxValueValidator,
    MinValueValidator,
)

from tubo_gestionAPP.validadores import (
    calcular_dias_computables,
    validar_codigo_unico_catalogo,
    validar_rango_fechas,
    validar_suma_ponderaciones,
)

from .feriados import feriados_entre


# Largo máximo de los campos de texto libre. TextField no aplica el
# límite por sí solo: se declara max_length (formulario y maxlength del
# HTML) y MaxLengthValidator (validación del modelo).
MAX_DESCRIPCION = 1000
MAX_OBSERVACIONES = 1000


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
        blank=True,
        max_length=MAX_DESCRIPCION,
        validators=[MaxLengthValidator(MAX_DESCRIPCION)],
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

        codigos_existentes = [
            codigo.upper()
            for codigo in CatalogoActividad.objects.exclude(
                pk=self.pk
            ).values_list("codigo", flat=True)
        ]

        try:
            validar_codigo_unico_catalogo(self.codigo, codigos_existentes)
        except ValidationError:
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

    def ponderaciones_activas(self, excluir_meta=None):
        """Ponderaciones de las metas activas del período."""
        if self.pk is None:
            return []

        metas = self.metas.filter(activo=True)

        if excluir_meta is not None:
            metas = metas.exclude(pk=excluir_meta)

        return list(metas.values_list("ponderacion", flat=True))

    def suma_ponderaciones(self):
        return sum(self.ponderaciones_activas(), Decimal("0"))

    def validar_cierre(self):
        """
        Un período solo puede cerrarse cuando sus metas activas suman
        exactamente 100%: así la evaluación final queda completa.
        """
        try:
            validar_suma_ponderaciones(self.ponderaciones_activas())
        except ValidationError:
            raise ValidationError({
                "cerrado": (
                    "No se puede cerrar el período: sus metas activas "
                    f"suman {self.suma_ponderaciones()}% y deben sumar "
                    "exactamente 100%."
                )
            })

    def clean(self):
        super().clean()

        if self.fecha_inicio and self.fecha_fin:
            try:
                validar_rango_fechas(self.fecha_inicio, self.fecha_fin)
            except ValidationError as error:
                raise ValidationError({"fecha_fin": error.messages})


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
        editable=False,
        verbose_name="Días computables",
        help_text=(
            "Se calcula automáticamente: días hábiles del rango, sin "
            "fines de semana ni feriados nacionales."
        )
    )

    observaciones = models.TextField(
        blank=True,
        max_length=MAX_OBSERVACIONES,
        validators=[MaxLengthValidator(MAX_OBSERVACIONES)],
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

        if self.fecha_inicio and self.fecha_fin:
            try:
                validar_rango_fechas(self.fecha_inicio, self.fecha_fin)
            except ValidationError as error:
                raise ValidationError({"fecha_fin": error.messages})

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

    def calcular_dias(self):
        """Días hábiles del rango, sin fines de semana ni feriados."""
        # Acepta también fechas en texto ("2026-01-31"), como las que se
        # pueden asignar desde el ORM antes de guardar.
        inicio = self._meta.get_field("fecha_inicio").to_python(self.fecha_inicio)
        fin = self._meta.get_field("fecha_fin").to_python(self.fecha_fin)

        if not (inicio and fin) or fin < inicio:
            return None

        return calcular_dias_computables(inicio, fin, feriados_entre(inicio, fin))

    def save(self, *args, **kwargs):
        # El valor nunca se escribe a mano: siempre se deriva del rango.
        self.dias_computables = self.calcular_dias()

        update_fields = kwargs.get("update_fields")
        if update_fields is not None:
            kwargs["update_fields"] = set(update_fields) | {"dias_computables"}

        super().save(*args, **kwargs)


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
        max_length=MAX_DESCRIPCION,
        validators=[MaxLengthValidator(MAX_DESCRIPCION)],
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

        # Las metas activas de un período no pueden superar el 100%.
        if (
            "ponderacion" not in errores
            and self.ponderacion is not None
            and self.activo
            and self.periodo_id
        ):
            disponible = 100 - sum(
                self.periodo.ponderaciones_activas(excluir_meta=self.pk),
                Decimal("0"),
            )

            if self.ponderacion > disponible:
                errores["ponderacion"] = (
                    "Las metas activas del período superarían el 100%. "
                    f"Ponderación disponible: {disponible}%."
                )

        if errores:
            raise ValidationError(errores)
