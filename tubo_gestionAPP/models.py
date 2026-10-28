from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class Compromiso(models.Model):
    ESTADOS = [
        ("verde", "Verde"),
        ("amarillo", "Amarillo"),
        ("rojo", "Rojo"),
    ]

    tarea = models.CharField(max_length=255)

    cumplimiento = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        verbose_name="Cumplimiento (%)",
    )

    estado = models.CharField(
        max_length=20,
        choices=ESTADOS,
        editable=False,
    )

    delegacion = models.ForeignKey(
        "delegacionesAPP.Delegacion",
        related_name="compromisos",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        verbose_name="Delegación",
    )

    # Baja logica: un compromiso no se elimina, se desactiva.
    activo = models.BooleanField(
        default=True,
        verbose_name="Activo",
    )

    class Meta:
        verbose_name = "Compromiso"
        verbose_name_plural = "Compromisos"
        ordering = ["-pk"]

    def __str__(self):
        return self.tarea

    @staticmethod
    def calcular_estado(cumplimiento):
        """
        Regla del semáforo acordada con la municipalidad:
          90% o más  -> verde
          60% a 89%  -> amarillo
          menos de 60% -> rojo
        """
        if cumplimiento >= 90:
            return "verde"

        if cumplimiento >= 60:
            return "amarillo"

        return "rojo"

    def clean(self):
        super().clean()

        self.tarea = (self.tarea or "").strip()

        if not self.tarea:
            raise ValidationError({
                "tarea": "La tarea del compromiso es obligatoria."
            })

        if self.cumplimiento is None:
            raise ValidationError({
                "cumplimiento": "Debe indicar el porcentaje de cumplimiento."
            })

        if not 0 <= self.cumplimiento <= 100:
            raise ValidationError({
                "cumplimiento": "El cumplimiento debe estar entre 0 y 100."
            })

    def save(self, *args, **kwargs):
        # El estado siempre se deriva del cumplimiento: nunca queda
        # un compromiso "verde" con 10% de avance.
        self.estado = self.calcular_estado(self.cumplimiento)
        super().save(*args, **kwargs)
