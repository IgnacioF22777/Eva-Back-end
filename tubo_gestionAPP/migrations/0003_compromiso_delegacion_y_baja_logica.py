from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("tubo_gestionAPP", "0002_alter_compromiso_tarea"),
        ("delegacionesAPP", "0003_baja_logica_y_servicio_protegido"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="compromiso",
            options={
                "ordering": ["-pk"],
                "verbose_name": "Compromiso",
                "verbose_name_plural": "Compromisos",
            },
        ),
        migrations.AddField(
            model_name="compromiso",
            name="delegacion",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="compromisos",
                to="delegacionesAPP.delegacion",
                verbose_name="Delegación",
            ),
        ),
        migrations.AddField(
            model_name="compromiso",
            name="activo",
            field=models.BooleanField(
                default=True,
                verbose_name="Activo",
            ),
        ),
        migrations.AlterField(
            model_name="compromiso",
            name="cumplimiento",
            field=models.PositiveSmallIntegerField(
                validators=[
                    MinValueValidator(0),
                    MaxValueValidator(100),
                ],
                verbose_name="Cumplimiento (%)",
            ),
        ),
        migrations.AlterField(
            model_name="compromiso",
            name="estado",
            field=models.CharField(
                choices=[
                    ("verde", "Verde"),
                    ("amarillo", "Amarillo"),
                    ("rojo", "Rojo"),
                ],
                editable=False,
                max_length=20,
            ),
        ),
    ]
