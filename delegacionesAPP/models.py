from django.db import models

class Delegacion(models.Model):
    nombre = models.CharField(max_length=100)
    direccion = models.CharField(max_length=200)
    encargado = models.CharField(max_length=100)
    email = models.EmailField(max_length=100)
    telefono = models.CharField(max_length=20)
    celular = models.CharField(max_length=20)

    def __str__(self):
        return self.nombre

class Servicio(models.Model):
    delegacion = models.ForeignKey(Delegacion, related_name='servicios', on_delete=models.CASCADE)
    nombre = models.CharField(max_length=100)

    def __str__(self):
        return f"{self.nombre} ({self.delegacion.nombre})"
