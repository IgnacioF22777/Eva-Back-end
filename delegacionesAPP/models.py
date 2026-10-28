from django.core.exceptions import ValidationError
from django.db import models


class Delegacion(models.Model):
    nombre = models.CharField(max_length=100)
    direccion = models.CharField(max_length=200)
    encargado = models.CharField(max_length=100)
    email = models.EmailField(max_length=100)
    telefono = models.CharField(max_length=20)
    celular = models.CharField(max_length=20)

    # Baja logica: una delegacion nunca se elimina, solo se desactiva.
    activo = models.BooleanField(
        default=True,
        verbose_name="Activa",
    )

    class Meta:
        verbose_name = "Delegación"
        verbose_name_plural = "Delegaciones"
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre

    def clean(self):
        super().clean()

        self.nombre = (self.nombre or "").strip()
        self.direccion = (self.direccion or "").strip()
        self.encargado = (self.encargado or "").strip()
        self.email = (self.email or "").strip().lower()
        self.telefono = (self.telefono or "").strip()
        self.celular = (self.celular or "").strip()

        if not self.nombre:
            raise ValidationError({
                "nombre": "El nombre de la delegación es obligatorio."
            })

    def puede_dar_de_baja(self):
        """
        Una delegación con servicios o compromisos activos no puede
        darse de baja: primero hay que reasignarlos o desactivarlos.
        """
        return not (
            self.servicios.filter(activo=True).exists()
            or self.compromisos.filter(activo=True).exists()
        )


class Servicio(models.Model):
    delegacion = models.ForeignKey(
        Delegacion,
        related_name="servicios",
        on_delete=models.PROTECT,
    )
    nombre = models.CharField(max_length=100)

    # Baja logica: se conserva el historial del servicio.
    activo = models.BooleanField(
        default=True,
        verbose_name="Activo",
    )

    class Meta:
        verbose_name = "Servicio"
        verbose_name_plural = "Servicios"
        ordering = ["nombre"]
        constraints = [
            models.UniqueConstraint(
                fields=["delegacion", "nombre"],
                name="unique_servicio_por_delegacion",
            )
        ]

    def __str__(self):
        return f"{self.nombre} ({self.delegacion.nombre})"

    def clean(self):
        super().clean()

        self.nombre = (self.nombre or "").strip()

        if not self.nombre:
            raise ValidationError({
                "nombre": "El nombre del servicio es obligatorio."
            })
