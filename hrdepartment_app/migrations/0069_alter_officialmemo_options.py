# Generated by Django 5.0.1 on 2024-03-14 14:29

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("hrdepartment_app", "0068_guidancedocuments"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="officialmemo",
            options={
                "ordering": ["-date_of_creation"],
                "verbose_name": "Служебная записка",
                "verbose_name_plural": "Служебные записки",
            },
        ),
    ]
