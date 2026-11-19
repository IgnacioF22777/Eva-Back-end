from django.db import models

from delegacionesAPP.models import Delegacion


# ============================================================
# EMERGENCIAS TERRITORIALES
# ============================================================
# Mantenedor 1: Zonas de riesgo de cada delegación.
# Mantenedor 2: Contactos de emergencia de cada delegación.
#
# Ningún registro se elimina: la baja es lógica (activo=False) y
# reversible, igual que en el resto del SGR. Las relaciones usan PROTECT
# para que borrar una delegación no arrastre zonas, alertas ni contactos.

class ZonaRiesgo(models.Model):
    NIVELES_PELIGRO = [
        ("bajo", "Bajo"),
        ("medio", "Medio"),
        ("alto", "Alto"),
        ("critico", "Crítico"),
    ]

    nombre = models.CharField(max_length=100)
    delegacion = models.ForeignKey(
        Delegacion,
        on_delete=models.PROTECT,
        related_name="zonas_riesgo",
    )
    descripcion_riesgo = models.TextField(max_length=500)
    nivel_peligro = models.CharField(
        max_length=20,
        choices=NIVELES_PELIGRO,
        default="medio",
    )
    # Dato sensible: la ubicación exacta de una zona de riesgo solo la ve
    # el Administrador en la API.
    coordenadas_aprox = models.CharField(max_length=100, blank=True, null=True)
    activo = models.BooleanField(default=True)

    class Meta:
        ordering = ["delegacion__nombre", "nombre"]
        verbose_name = "zona de riesgo"
        verbose_name_plural = "zonas de riesgo"

    def __str__(self):
        return f"{self.nombre} - {self.delegacion.nombre}"

    def puede_dar_de_baja(self):
        """
        Una zona con contactos asignados o reportes en curso no se da de
        baja: primero hay que reasignarlos o cerrarlos.
        """
        return not (
            self.contactos.filter(activo=True).exists()
            or self.reportes.filter(activo=True)
            .exclude(estado="resuelto")
            .exists()
        )


class Alerta(models.Model):
    NIVELES_ALERTA = [
        ("preventiva", "Preventiva"),
        ("alerta", "Alerta"),
        ("emergencia", "Emergencia"),
    ]

    tipo_evento = models.CharField(max_length=100)
    nivel = models.CharField(
        max_length=20,
        choices=NIVELES_ALERTA,
        default="preventiva",
    )
    zona = models.ForeignKey(
        ZonaRiesgo,
        on_delete=models.PROTECT,
        related_name="alertas",
    )
    descripcion = models.TextField(max_length=500)
    fecha_inicio = models.DateTimeField(auto_now_add=True)
    fecha_fin = models.DateTimeField(null=True, blank=True)
    estado = models.BooleanField(default=True)

    def __str__(self):
        return f"[{self.get_nivel_display()}] {self.tipo_evento} en {self.zona.nombre}"


class ContactoEmergencia(models.Model):
    nombre = models.CharField(max_length=100)
    cargo = models.CharField(max_length=100)
    # Datos sensibles: teléfono y correo personales del contacto. En la
    # API solo los ve el Administrador.
    telefono = models.CharField(max_length=20)
    email = models.EmailField(max_length=100, blank=True)
    delegacion = models.ForeignKey(
        Delegacion,
        on_delete=models.PROTECT,
        related_name="contactos_emergencia",
    )
    zona_asignada = models.ForeignKey(
        ZonaRiesgo,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="contactos",
    )
    activo = models.BooleanField(default=True)

    class Meta:
        ordering = ["delegacion__nombre", "nombre"]
        verbose_name = "contacto de emergencia"
        verbose_name_plural = "contactos de emergencia"

    def __str__(self):
        return f"{self.nombre} ({self.cargo}) - {self.delegacion.nombre}"

    def puede_dar_de_baja(self):
        """Un contacto con reportes derivados en curso no se da de baja."""
        return not (
            self.reportes.filter(activo=True, estado="derivado").exists()
        )
