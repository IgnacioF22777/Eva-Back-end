from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("delegacionesAPP", "0002_alter_delegacion_direccion_and_more"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="delegacion",
            options={
                "ordering": ["nombre"],
                "verbose_name": "Delegación",
                "verbose_name_plural": "Delegaciones",
            },
        ),
        migrations.AlterModelOptions(
            name="servicio",
            options={
                "ordering": ["nombre"],
                "verbose_name": "Servicio",
                "verbose_name_plural": "Servicios",
            },
        ),
        migrations.AddField(
            model_name="delegacion",
            name="activo",
            field=models.BooleanField(
                default=True,
                verbose_name="Activa",
            ),
        ),
        migrations.AddField(
            model_name="servicio",
            name="activo",
            field=models.BooleanField(
                default=True,
                verbose_name="Activo",
            ),
        ),
        migrations.AlterField(
            model_name="servicio",
            name="delegacion",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="servicios",
                to="delegacionesAPP.delegacion",
            ),
        ),
        migrations.AddConstraint(
            model_name="servicio",
            constraint=models.UniqueConstraint(
                fields=("delegacion", "nombre"),
                name="unique_servicio_por_delegacion",
            ),
        ),
    ]
