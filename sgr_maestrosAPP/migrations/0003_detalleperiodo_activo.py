from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("sgr_maestrosAPP", "0002_periodo_meta_detalleperiodo_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="detalleperiodo",
            name="activo",
            field=models.BooleanField(
                default=True,
                verbose_name="Activo",
            ),
        ),
    ]
