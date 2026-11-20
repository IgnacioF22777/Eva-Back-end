from datetime import date

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone

from delegacionesAPP.models import Delegacion
from seguridadAPP.models import formatear_rut, normalizar_rut
from tubo_gestionAPP.validadores import validar_rut_chileno


# ============================================================
# REGALOS PARA NIÑOS (EVALUACIÓN 3)
# ============================================================
# Responsable: Camilo Villalobos.
#
# Respuestas del profesor:
#   - Datos del niño: RUT, nombre, apellido, sexo y fecha de nacimiento.
#   - Los inscribe el funcionario.
#   - Un RUT se inscribe una sola vez por campaña, entre todas las
#     delegaciones ("RUT ya ingresado por Delegación XX").
#   - Cada delegación ve solo a los niños que inscribió.


def edad_en(fecha_nacimiento, fecha):
    """Años cumplidos a una fecha."""
    return fecha.year - fecha_nacimiento.year - (
        (fecha.month, fecha.day) < (fecha_nacimiento.month, fecha_nacimiento.day)
    )


class CampanaRegalo(models.Model):
    NAVIDAD = "NAVIDAD"
    DIA_NINO = "DIA_NINO"
    ANIVERSARIO = "ANIVERSARIO"
    TIPOS = [
        (NAVIDAD, "Navidad"),
        (DIA_NINO, "Día del Niño"),
        (ANIVERSARIO, "Aniversario"),
    ]

    tipo = models.CharField("Campaña", max_length=12, choices=TIPOS)
    anio = models.PositiveSmallIntegerField(
        "Año",
        validators=[MinValueValidator(2020), MaxValueValidator(2100)],
    )
    fecha_inicio = models.DateField("Inscripciones desde")
    fecha_fin = models.DateField(
        "Inscripciones hasta",
        help_text="También es la fecha con que se calcula la edad del niño.",
    )
    edad_maxima = models.PositiveSmallIntegerField(
        "Edad máxima (años)",
        default=12,
        validators=[MinValueValidator(0), MaxValueValidator(17)],
        help_text="El niño no puede tener más de esta edad a la fecha de cierre.",
    )
    activo = models.BooleanField("Vigente", default=True)

    class Meta:
        verbose_name = "Campaña de regalos"
        verbose_name_plural = "Campañas de regalos"
        ordering = ["-anio", "tipo"]
        constraints = [
            models.UniqueConstraint(
                fields=["tipo", "anio"], name="campana_unica_por_tipo_y_anio"
            ),
        ]

    def __str__(self):
        return f"{self.get_tipo_display()} {self.anio}"

    def clean(self):
        if self.fecha_inicio and self.fecha_fin and self.fecha_fin < self.fecha_inicio:
            raise ValidationError(
                {"fecha_fin": "La fecha de cierre no puede ser anterior a la de inicio."}
            )

    def inscripciones_abiertas(self, hoy=None):
        hoy = hoy or timezone.localdate()
        return self.activo and self.fecha_inicio <= hoy <= self.fecha_fin


class NinoInscrito(models.Model):
    FEMENINO = "F"
    MASCULINO = "M"
    SEXOS = [
        (FEMENINO, "Femenino"),
        (MASCULINO, "Masculino"),
    ]

    campana = models.ForeignKey(
        CampanaRegalo,
        on_delete=models.PROTECT,
        related_name="inscritos",
        verbose_name="Campaña",
    )
    rut = models.CharField("RUT del niño", max_length=12)
    nombre = models.CharField("Nombre", max_length=80)
    apellido = models.CharField("Apellido", max_length=80)
    sexo = models.CharField("Sexo", max_length=1, choices=SEXOS)
    fecha_nacimiento = models.DateField("Fecha de nacimiento")

    # Los pone el sistema: no vienen del formulario.
    delegacion = models.ForeignKey(
        Delegacion,
        on_delete=models.PROTECT,
        related_name="ninos_inscritos",
        editable=False,
        null=True,
    )
    registrado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="ninos_inscritos",
        editable=False,
        null=True,
    )
    fecha_registro = models.DateTimeField(auto_now_add=True)
    activo = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Niño inscrito"
        verbose_name_plural = "Niños inscritos"
        ordering = ["apellido", "nombre"]
        indexes = [models.Index(fields=["campana", "rut"])]

    def __str__(self):
        return f"{self.nombre} {self.apellido} ({self.rut_formateado})"

    @property
    def rut_formateado(self):
        return formatear_rut(self.rut)

    @property
    def edad(self):
        if not self.fecha_nacimiento or not self.campana_id:
            return None
        return edad_en(self.fecha_nacimiento, self.campana.fecha_fin)

    def duplicado(self):
        """Inscripción vigente del mismo RUT en la misma campaña (otra fila)."""
        return (
            NinoInscrito.objects.filter(
                campana_id=self.campana_id, rut=self.rut, activo=True
            )
            .exclude(pk=self.pk)
            .select_related("delegacion")
            .first()
        )

    def clean(self):
        errores = {}

        if self.rut:
            self.rut = normalizar_rut(self.rut)
            try:
                validar_rut_chileno(self.rut)
            except ValidationError as error:
                errores["rut"] = error.messages

        self.nombre = (self.nombre or "").strip()
        self.apellido = (self.apellido or "").strip()

        if self.fecha_nacimiento:
            if self.fecha_nacimiento > timezone.localdate():
                errores["fecha_nacimiento"] = "La fecha de nacimiento no puede ser futura."
            elif self.campana_id:
                edad = edad_en(self.fecha_nacimiento, self.campana.fecha_fin)
                if edad > self.campana.edad_maxima:
                    errores["fecha_nacimiento"] = (
                        f"El niño tendrá {edad} años al cierre de la campaña; "
                        f"el máximo es {self.campana.edad_maxima}."
                    )

        if self.campana_id and self.pk is None and not self.campana.inscripciones_abiertas():
            errores["campana"] = "Las inscripciones de esta campaña no están abiertas."

        if self.activo and self.campana_id and self.rut and "rut" not in errores:
            otro = self.duplicado()
            if otro:
                donde = otro.delegacion.nombre if otro.delegacion else "otra delegación"
                errores["rut"] = (
                    f"RUT ya ingresado por {donde} en la campaña {self.campana}."
                )

        if errores:
            raise ValidationError(errores)
