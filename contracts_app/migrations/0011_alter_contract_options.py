# Generated by Django 5.0.6 on 2024-06-13 14:13

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("contracts_app", "0010_alter_contract_date_conclusion"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="contract",
            options={
                "ordering": ["-date_conclusion"],
                "verbose_name": "Договор",
                "verbose_name_plural": "Договора",
            },
        ),
    ]
