# Generated by Django 5.0.6 on 2024-07-11 14:04

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("contracts_app", "0014_alter_contract_doc_file"),
    ]

    operations = [
        migrations.AlterField(
            model_name="contract",
            name="date_entry",
            field=models.DateField(
                auto_now_add=True, verbose_name="Дата ввода информации"
            ),
        ),
    ]
