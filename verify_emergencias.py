from emergenciasTerritorialesAPP.models import ZonaRiesgo, Alerta, ContactoEmergencia
print(f"Zonas: {ZonaRiesgo.objects.count()}")
print(f"Alertas: {Alerta.objects.count()}")
print(f"Contactos: {ContactoEmergencia.objects.count()}")
