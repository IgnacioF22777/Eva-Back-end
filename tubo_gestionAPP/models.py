from django.conf import settings
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
        default=0,
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

    servicio = models.ForeignKey(
        "delegacionesAPP.Servicio",
        related_name="compromisos",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        verbose_name="Servicio",
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

        # Un compromiso puede estar sin asignar, pero si tiene servicio
        # debe tener delegación y ambos deben ser coherentes.
        if self.servicio_id and not self.delegacion_id:
            raise ValidationError({
                "servicio": (
                    "Debe indicar la delegación antes de asignar un servicio."
                )
            })

        if (
            self.servicio_id
            and self.delegacion_id
            and self.servicio.delegacion_id != self.delegacion_id
        ):
            raise ValidationError({
                "servicio": (
                    "El servicio seleccionado no pertenece a la delegación."
                )
            })

    def save(self, *args, **kwargs):
        # El estado siempre se deriva del cumplimiento: nunca queda
        # un compromiso "verde" con 10% de avance.
        self.estado = self.calcular_estado(self.cumplimiento)

        # Si se guarda con update_fields (por ejemplo, tras registrar un
        # avance), el estado debe persistirse en la misma operación.
        update_fields = kwargs.get("update_fields")
        if update_fields is not None:
            kwargs["update_fields"] = set(update_fields) | {"estado"}

        super().save(*args, **kwargs)


class AsignacionCompromiso(models.Model):
    """
    Historial de asignaciones de un compromiso a una delegación y servicio.

    La asignación vigente se marca con ``activo=True``. Al reasignar, la
    anterior se desactiva (nunca se elimina) y se crea una nueva.
    """

    compromiso = models.ForeignKey(
        "Compromiso",
        related_name="asignaciones",
        on_delete=models.PROTECT,
        verbose_name="Compromiso",
    )

    delegacion = models.ForeignKey(
        "delegacionesAPP.Delegacion",
        related_name="asignaciones_compromiso",
        on_delete=models.PROTECT,
        verbose_name="Delegación",
    )

    servicio = models.ForeignKey(
        "delegacionesAPP.Servicio",
        related_name="asignaciones_compromiso",
        on_delete=models.PROTECT,
        verbose_name="Servicio",
    )

    usuario_asignador = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="asignaciones_compromiso_realizadas",
        on_delete=models.PROTECT,
        verbose_name="Asignado por",
    )

    fecha_asignacion = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Fecha de asignación",
    )

    observacion = models.TextField(
        blank=True,
        verbose_name="Observación",
    )

    # Baja logica: la asignación anterior se conserva como historial.
    activo = models.BooleanField(
        default=True,
        verbose_name="Asignación vigente",
    )

    class Meta:
        verbose_name = "Asignación de compromiso"
        verbose_name_plural = "Asignaciones de compromisos"
        ordering = ["-fecha_asignacion", "-pk"]
        indexes = [
            models.Index(
                fields=["compromiso", "activo"],
                name="asig_compromiso_activo_idx",
            ),
        ]

    def __str__(self):
        return (
            f"{self.compromiso} -> {self.delegacion} / {self.servicio}"
        )

    def clean(self):
        super().clean()

        if (
            self.servicio_id
            and self.delegacion_id
            and self.servicio.delegacion_id != self.delegacion_id
        ):
            raise ValidationError({
                "servicio": (
                    "El servicio seleccionado no pertenece a la delegación."
                )
            })


class RegistroAvance(models.Model):
    """
    Historial de avances de un compromiso.

    Cada registro conserva el porcentaje informado, la evidencia y el
    usuario que lo registró. El compromiso se actualiza en la misma
    transacción atómica.
    """

    compromiso = models.ForeignKey(
        "Compromiso",
        related_name="avances",
        on_delete=models.PROTECT,
        verbose_name="Compromiso",
    )

    usuario_registro = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="avances_compromiso_registrados",
        on_delete=models.PROTECT,
        verbose_name="Registrado por",
    )

    porcentaje_avance = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        verbose_name="Porcentaje de avance (%)",
    )

    evidencia = models.TextField(
        verbose_name="Evidencia",
        help_text=(
            "Referencia verificable: acta, correo, fotografía, "
            "documento o enlace."
        ),
    )

    observacion = models.TextField(
        blank=True,
        verbose_name="Observación",
    )

    fecha_registro = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Fecha de registro",
    )

    class Meta:
        verbose_name = "Registro de avance"
        verbose_name_plural = "Registros de avance"
        ordering = ["-fecha_registro", "-pk"]
        indexes = [
            models.Index(
                fields=["compromiso", "fecha_registro"],
                name="avance_compromiso_fecha_idx",
            ),
        ]

    def __str__(self):
        fecha = (
            self.fecha_registro.strftime("%d-%m-%Y %H:%M")
            if self.fecha_registro
            else "sin fecha"
        )
        return f"{self.compromiso} - {self.porcentaje_avance}% ({fecha})"

    def clean(self):
        super().clean()

        if not (self.evidencia or "").strip():
            raise ValidationError({
                "evidencia": "La evidencia del avance es obligatoria."
            })
