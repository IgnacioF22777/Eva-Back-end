from django.core.management import call_command
from django.db import migrations


def crear_tabla_cache(apps, schema_editor):
    """
    Crea la tabla de la caché compartida (settings.CACHES). Se hace en una
    migración para que `migrate` la cree en cada despliegue y nadie tenga
    que acordarse de ejecutar `createcachetable`. Si ya existe, no hace
    nada.
    """
    call_command(
        "createcachetable",
        database=schema_editor.connection.alias,
        verbosity=0,
    )


class Migration(migrations.Migration):

    dependencies = [
        ("seguridadAPP", "0003_cargo"),
    ]

    operations = [
        migrations.RunPython(crear_tabla_cache, migrations.RunPython.noop),
    ]
