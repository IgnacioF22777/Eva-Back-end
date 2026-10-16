from django.core.management.base import BaseCommand

from seguridadAPP.roles import sincronizar_roles


class Command(BaseCommand):
    help = "Crea los roles del SGR (grupos de Django) con sus permisos base."

    def handle(self, *args, **options):
        for nombre_rol, creado, faltantes in sincronizar_roles():
            estado = "creado" if creado else "actualizado"
            self.stdout.write(self.style.SUCCESS(f"Rol {nombre_rol}: {estado}"))

            for permiso in faltantes:
                self.stdout.write(self.style.WARNING(
                    f"  Permiso no encontrado: {permiso}"
                ))
