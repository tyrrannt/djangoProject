# Generated by Django 5.0.6 on 2024-06-05 12:58

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("contracts_app", "0008_alter_companyproperty_options"),
    ]

    operations = [
        migrations.AddField(
            model_name="contract",
            name="official_information",
            field=models.CharField(
                blank=True,
                default="",
                max_length=400,
                verbose_name="Служебная информация",
            ),
        ),
    ]