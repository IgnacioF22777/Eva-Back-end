import json
import os
from django.core.management.base import BaseCommand
from django.conf import settings
from delegacionesAPP.models import Delegacion, Servicio
from tubo_gestionAPP.models import Compromiso

class Command(BaseCommand):
    help = 'Importa datos desde archivos JSON a la base de datos'

    def handle(self, *args, **kwargs):
        # Importar Delegaciones
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

        # Importar Compromisos
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
