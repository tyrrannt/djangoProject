# Generated by Django 5.0.6 on 2024-06-24 06:23

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("customers_app", "0053_counteragentdocuments"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="counteragent",
            options={
                "ordering": ["short_name"],
                "verbose_name": "Контрагент",
                "verbose_name_plural": "Контрагенты",
            },
        ),
    ]
