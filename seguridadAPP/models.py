from django.conf import settings
from django.db import models
from django.core.exceptions import ValidationError

from delegacionesAPP.models import Delegacion
from tubo_gestionAPP.validadores import validar_rut_chileno


# ============================================================
# UTILIDADES DE RUT
# ============================================================

def normalizar_rut(rut: str) -> str:
    """Convierte '12.345.678-k' en '12345678-K' (formato de almacenamiento)."""
    limpio = (rut or "").replace(".", "").replace("-", "").replace(" ", "")
    limpio = limpio.strip().upper()

    if len(limpio) < 2:
        return limpio

    return f"{limpio[:-1]}-{limpio[-1]}"


def formatear_rut(rut: str) -> str:
    """Convierte '12345678-K' en '12.345.678-K' para mostrar en pantalla."""
    if not rut or "-" not in rut:
        return rut or ""

    cuerpo, dv = rut.split("-")
    cuerpo = f"{int(cuerpo):,}".replace(",", ".")
    return f"{cuerpo}-{dv}"


# ============================================================
# MODELO: PERFIL DE USUARIO (FUNCIONARIO)
# ============================================================
# Se extiende el User de Django con una relación uno a uno para no
# reemplazar AUTH_USER_MODEL en una base de datos que ya está migrada.
# Los roles se manejan con los Grupos (Group) y Permisos de Django.

class PerfilUsuario(models.Model):

    usuario = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="perfil",
        verbose_name="Usuario"
    )

    rut = models.CharField(
        max_length=12,
        unique=True,
        verbose_name="RUT",
        help_text="Formato: 12.345.678-5"
    )

    delegacion = models.ForeignKey(
        Delegacion,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="funcionarios",
        verbose_name="Delegación"
    )

    cargo = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="Cargo"
    )

    class Meta:
        verbose_name = "Perfil de usuario"
        verbose_name_plural = "Perfiles de usuario"
        ordering = ["usuario__last_name", "usuario__first_name"]

    def __str__(self):
        return f"{self.rut_formateado} - {self.usuario.get_full_name()}"

    @property
    def rut_formateado(self):
        return formatear_rut(self.rut)

    def clean(self):
        super().clean()

        self.rut = normalizar_rut(self.rut)

        try:
            validar_rut_chileno(self.rut)
        except ValidationError as error:
            raise ValidationError({"rut": error.messages})

        if PerfilUsuario.objects.exclude(
            pk=self.pk
        ).filter(
            rut=self.rut
        ).exists():
            raise ValidationError({
                "rut": "Ya existe un usuario registrado con este RUT."
            })
