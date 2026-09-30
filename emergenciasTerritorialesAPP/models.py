from django.db import models
from delegacionesAPP.models import Delegacion

class ZonaRiesgo(models.Model):
    nombre = models.CharField(max_length=100)
    delegacion = models.ForeignKey(Delegacion, on_delete=models.CASCADE, related_name='zonas_riesgo')
    descripcion_riesgo = models.TextField(max_length=500)
    nivel_peligro = models.CharField(
        max_length=20, 
        choices=[('bajo', 'Bajo'), ('medio', 'Medio'), ('alto', 'Alto'), ('critico', 'Crítico')],
        default='medio'
    )
    coordenadas_aprox = models.CharField(max_length=100, blank=True, null=True)

    def __str__(self):
        return f"{self.nombre} - {self.delegacion.nombre}"

class Alerta(models.Model):
    NIVELES_ALERTA = [
        ('preventiva', 'Preventiva'),
        ('alerta', 'Alerta'),
        ('emergencia', 'Emergencia'),
    ]
    
    tipo_evento = models.CharField(max_length=100) 
    nivel = models.CharField(max_length=20, choices=NIVELES_ALERTA, default='preventiva')
    zona = models.ForeignKey(ZonaRiesgo, on_delete=models.CASCADE, related_name='alertas')
    descripcion = models.TextField(max_length=500)
    fecha_inicio = models.DateTimeField(auto_now_add=True)
    fecha_fin = models.DateTimeField(null=True, blank=True)
    estado = models.BooleanField(default=True)

    def __str__(self):
        return f"[{self.get_nivel_display()}] {self.tipo_evento} en {self.zona.nombre}"

class ContactoEmergencia(models.Model):
    nombre = models.CharField(max_length=100)
    cargo = models.CharField(max_length=100)
    telefono = models.CharField(max_length=20)
    delegacion = models.ForeignKey(Delegacion, on_delete=models.CASCADE, related_name='contactos_emergencia')
    zona_asignada = models.ForeignKey(ZonaRiesgo, on_delete=models.SET_NULL, null=True, blank=True)

    def __str__(self):
        return f"{self.nombre} ({self.cargo}) - {self.delegacion.nombre}"
