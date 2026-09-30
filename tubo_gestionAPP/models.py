from django.db import models

class Compromiso(models.Model):
    ESTADOS = [
        ('verde', 'Verde'),
        ('amarillo', 'Amarillo'),
        ('rojo', 'Rojo'),
    ]
    tarea = models.CharField(max_length=255)
    cumplimiento = models.IntegerField()
    estado = models.CharField(max_length=20, choices=ESTADOS)

    def __str__(self):
        return self.tarea
