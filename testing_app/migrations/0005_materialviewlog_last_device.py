# Generated manually for testing_app

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("testing_app", "0004_lecturematerial_videolecture_materialviewlog"),
    ]

    operations = [
        migrations.AddField(
            model_name="materialviewlog",
            name="last_device",
            field=models.CharField(
                blank=True,
                default="",
                max_length=50,
                verbose_name="Устройство",
            ),
        ),
    ]
