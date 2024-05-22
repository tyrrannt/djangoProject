# Generated by Django 5.0.3 on 2024-04-27 17:39

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("logistics_app", "0015_alter_package_options"),
    ]

    operations = [
        migrations.CreateModel(
            name="PackageImage",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "date_of_creation",
                    models.DateField(
                        auto_now_add=True, verbose_name="Дата и время создания"
                    ),
                ),
                ("image", models.ImageField(upload_to="", verbose_name="")),
                (
                    "caption",
                    models.CharField(default="", max_length=200, verbose_name=""),
                ),
                (
                    "package",
                    models.ForeignKey(
                        blank=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        to="logistics_app.package",
                        verbose_name="",
                    ),
                ),
            ],
            options={
                "verbose_name": "",
                "verbose_name_plural": "",
                "ordering": ["-date_of_creation"],
            },
        ),
    ]
