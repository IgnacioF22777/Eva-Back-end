from django.conf import settings
from django.db import models

from delegacionesAPP.models import Delegacion
from emergenciasTerritorialesAPP.models import ContactoEmergencia, ZonaRiesgo


# ============================================================
# REPORTES CIUDADANOS
# ============================================================
# Transacción del negocio: DERIVACIÓN DEL REPORTE CIUDADANO.
#
# Un vecino informa un problema (bache, luminaria, basura, seguridad...).
# El reporte se registra como "pendiente" y luego el Supervisor lo deriva
# a una zona de riesgo y a un contacto de emergencia de la misma
# delegación. Cada derivación queda en el historial (DerivacionReporte);
# al rederivar, la anterior queda como histórica y nunca se elimina.
# Finalmente el reporte se marca como resuelto.
#
# El estado, la zona y el contacto del reporte SOLO cambian por la
# transacción (ver reportesCiudadanosAPP/transaccion.py), nunca editando
# el reporte directamente.

class ReporteCiudadano(models.Model):
    TIPO_REPORTE = [
        ("alumbrado", "Alumbrado Público"),
        ("baches", "Baches y Pavimento"),
        ("basura", "Recolección de Residuos"),
        ("seguridad", "Seguridad Ciudadana"),
        ("verde", "Áreas Verdes"),
        ("otros", "Otros"),
    ]

    PRIORIDAD = [
        ("alta", "Alta"),
        ("media", "Media"),
        ("baja", "Baja"),
    ]

    ESTADO = [
        ("pendiente", "Pendiente"),
        ("analisis", "En Análisis"),
        ("derivado", "Derivado a Departamento"),
        ("resuelto", "Resuelto"),
    ]

    delegacion = models.ForeignKey(
        Delegacion,
        on_delete=models.PROTECT,
        related_name="reportes",
    )
    tipo = models.CharField(max_length=20, choices=TIPO_REPORTE)
    descripcion = models.TextField(max_length=500)
    ubicacion = models.CharField(max_length=200)
    prioridad = models.CharField(max_length=10, choices=PRIORIDAD, default="media")
    estado = models.CharField(max_length=20, choices=ESTADO, default="pendiente")
    fecha_reporte = models.DateTimeField(auto_now_add=True)
    fecha_resolucion = models.DateTimeField(null=True, blank=True)

    # Vecino que informa. Son datos personales: en la API solo los ve el
    # Administrador.
    nombre_vecino = models.CharField(max_length=100, blank=True)
    telefono_vecino = models.CharField(max_length=20, blank=True)
    email_vecino = models.EmailField(max_length=100, blank=True)

    # Derivación vigente (la escribe solo la transacción).
    zona = models.ForeignKey(
        ZonaRiesgo,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="reportes",
    )
    contacto = models.ForeignKey(
        ContactoEmergencia,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="reportes",
    )

    activo = models.BooleanField(default=True)

    class Meta:
        ordering = ["-fecha_reporte"]
        verbose_name = "reporte ciudadano"
        verbose_name_plural = "reportes ciudadanos"

    def __str__(self):
        return f"{self.tipo} - {self.delegacion.nombre} ({self.estado})"

    @property
    def esta_resuelto(self):
        return self.estado == "resuelto"


class DerivacionReporte(models.Model):
    """Historial de la transacción: cada derivación de un reporte."""

    reporte = models.ForeignKey(
        ReporteCiudadano,
        on_delete=models.PROTECT,
        related_name="derivaciones",
    )
    zona = models.ForeignKey(
        ZonaRiesgo,
        on_delete=models.PROTECT,
        related_name="derivaciones",
    )
    contacto = models.ForeignKey(
        ContactoEmergencia,
        on_delete=models.PROTECT,
        related_name="derivaciones",
    )
    observacion = models.TextField(max_length=1000, blank=True)
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="derivaciones_reporte",
    )
    fecha = models.DateTimeField(auto_now_add=True)

    # True = derivación vigente; False = histórica o anulada.
    activo = models.BooleanField(default=True)
    anulada = models.BooleanField(default=False)

    class Meta:
        ordering = ["-fecha", "-pk"]
        verbose_name = "derivación de reporte"
        verbose_name_plural = "derivaciones de reportes"

    def __str__(self):
        return f"Reporte {self.reporte_id} -> {self.zona.nombre} / {self.contacto.nombre}"
