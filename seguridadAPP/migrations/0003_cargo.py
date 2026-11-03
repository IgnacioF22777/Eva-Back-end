import django.db.models.deletion
from django.db import migrations, models


def copiar_cargos(apps, schema_editor):
    """Convierte el cargo escrito como texto en registros de Cargo."""
    Cargo = apps.get_model("seguridadAPP", "Cargo")
    PerfilUsuario = apps.get_model("seguridadAPP", "PerfilUsuario")

    cargos = {}

    for perfil in PerfilUsuario.objects.exclude(cargo_texto="").exclude(
        cargo_texto__isnull=True
    ):
        nombre = " ".join(perfil.cargo_texto.split())
        if not nombre:
            continue

        clave = nombre.lower()
        if clave not in cargos:
            cargos[clave] = Cargo.objects.create(nombre=nombre)

        perfil.cargo = cargos[clave]
        perfil.save(update_fields=["cargo"])


def restaurar_cargos(apps, schema_editor):
    PerfilUsuario = apps.get_model("seguridadAPP", "PerfilUsuario")

    for perfil in PerfilUsuario.objects.select_related("cargo").exclude(
        cargo__isnull=True
    ):
        perfil.cargo_texto = perfil.cargo.nombre
        perfil.save(update_fields=["cargo_texto"])


class Migration(migrations.Migration):

    dependencies = [
        ("seguridadAPP", "0002_perfiles_acceso"),
    ]

    operations = [
        migrations.CreateModel(
            name="Cargo",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("nombre", models.CharField(max_length=100, unique=True, verbose_name="Nombre del cargo")),
                ("descripcion", models.CharField(blank=True, max_length=255, verbose_name="Descripción")),
                ("activo", models.BooleanField(default=True, verbose_name="Activo")),
            ],
            options={
                "verbose_name": "Cargo",
                "verbose_name_plural": "Cargos",
                "ordering": ["nombre"],
            },
        ),
        migrations.RenameField(
            model_name="perfilusuario",
            old_name="cargo",
            new_name="cargo_texto",
        ),
        migrations.AddField(
            model_name="perfilusuario",
            name="cargo",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="funcionarios",
                to="seguridadAPP.cargo",
                verbose_name="Cargo",
            ),
        ),
        migrations.RunPython(copiar_cargos, restaurar_cargos),
        migrations.RemoveField(
            model_name="perfilusuario",
            name="cargo_texto",
        ),
    ]
