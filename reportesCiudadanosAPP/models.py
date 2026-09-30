from django.db import models
from delegacionesAPP.models import Delegacion

class ReporteCiudadano(models.Model):
    TIPO_REPORTE = [
        ('alumbrado', 'Alumbrado Público'),
        ('baches', 'Baches y Pavimento'),
        ('basura', 'Recolección de Residuos'),
        ('seguridad', 'Seguridad Ciudadana'),
        ('verde', 'Áreas Verdes'),
        ('otros', 'Otros'),
    ]
    
    PRIORIDAD = [
        ('alta', 'Alta'),
        ('media', 'Media'),
        ('baja', 'Baja'),
    ]
    
    ESTADO = [
        ('pendiente', 'Pendiente'),
        ('analisis', 'En Análisis'),
        ('derivado', 'Derivado a Departamento'),
        ('resuelto', 'Resuelto'),
    ]

    delegacion = models.ForeignKey(Delegacion, on_delete=models.CASCADE, related_name='reportes')
    tipo = models.CharField(max_length=20, choices=TIPO_REPORTE)
    descripcion = models.TextField(max_length=500)
    ubicacion = models.CharField(max_length=200)
    prioridad = models.CharField(max_length=10, choices=PRIORIDAD, default='media')
    estado = models.CharField(max_length=20, choices=ESTADO, default='pendiente')
    fecha_reporte = models.DateTimeField(auto_now_add=True)
    fecha_resolucion = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.tipo} - {self.delegacion.nombre} ({self.estado})"
