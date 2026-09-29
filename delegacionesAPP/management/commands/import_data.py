import json
import os
from django.core.management.base import BaseCommand
from django.conf import settings
from delegacionesAPP.models import Delegacion, Servicio
from tubo_gestionAPP.models import Compromiso
from emergenciasTerritorialesAPP.models import ZonaRiesgo, Alerta, ContactoEmergencia

class Command(BaseCommand):
    help = 'Importa datos desde archivos JSON y añade datos de prueba'

    def handle(self, *args, **kwargs):
        # Importar Delegaciones (Solo si no existen)
        if not Delegacion.objects.exists():
            delegaciones_file = os.path.join(settings.BASE_DIR, 'data', 'delegaciones.json')
            with open(delegaciones_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                for item in data:
                    delegacion = Delegacion.objects.create(
                        nombre=item['nombre'],
                        direccion=item['direccion'],
                        encargado=item['encargado'],
                        email=item['email'],
                        telefono=item['telefono'],
                        celular=item['celular']
                    )
                    for servicio_nombre in item['servicios']:
                        Servicio.objects.create(delegacion=delegacion, nombre=servicio_nombre)
            self.stdout.write(self.style.SUCCESS('Delegaciones importadas correctamente.'))

        # Importar Compromisos (Solo si no existen)
        if not Compromiso.objects.exists():
            compromisos_file = os.path.join(settings.BASE_DIR, 'data', 'compromisos.json')
            with open(compromisos_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                for item in data:
                    Compromiso.objects.create(
                        tarea=item['tarea'],
                        cumplimiento=item['cumplimiento'],
                        estado=item['estado']
                    )
            self.stdout.write(self.style.SUCCESS('Compromisos importados correctamente.'))

        # Añadir datos de ejemplo para Emergencias
        if not ZonaRiesgo.objects.exists():
            delegacion = Delegacion.objects.first() # Usamos la primera delegación disponible
            if delegacion:
                zona = ZonaRiesgo.objects.create(
                    nombre="Cerro Grande - Riesgo Incendio",
                    delegacion=delegacion,
                    descripcion_riesgo="Alta presencia de pastizales secos",
                    nivel_peligro="alto"
                )
                Alerta.objects.create(
                    tipo_evento="Incendio Forestal",
                    nivel="alerta",
                    zona=zona,
                    descripcion="Prevención por altas temperaturas"
                )
                ContactoEmergencia.objects.create(
                    nombre="Central Bomberos La Serena",
                    cargo="Unidad de Emergencia",
                    telefono="132",
                    delegacion=delegacion,
                    zona_asignada=zona
                )
                self.stdout.write(self.style.SUCCESS('Datos de EmergenciasTerritoriales añadidos correctamente.'))
