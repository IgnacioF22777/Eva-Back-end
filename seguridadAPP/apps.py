from django.apps import AppConfig
from django.db.models.signals import post_migrate


def sincronizar_roles_post_migrate(sender, **kwargs):
    """
    Después de cada `migrate` se asegura de que los tres perfiles
    existan con sus permisos base. Evita que un despliegue quede con
    grupos sin permisos por olvidar ejecutar `crear_roles`.
    """
    from .roles import sincronizar_roles

    sincronizar_roles()


class SeguridadappConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'seguridadAPP'
    verbose_name = 'Seguridad: usuarios y roles'

    def ready(self):
        post_migrate.connect(
            sincronizar_roles_post_migrate,
            sender=self,
            dispatch_uid="seguridadAPP.sincronizar_roles",
        )
