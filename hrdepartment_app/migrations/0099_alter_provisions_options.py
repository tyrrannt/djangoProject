# Generated by Django 5.0.6 on 2024-06-21 10:39

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("hrdepartment_app", "0098_alter_provisions_options"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="provisions",
            options={
                "ordering": ["-document_date"],
                "verbose_name": "Положение",
                "verbose_name_plural": "Положения",
            },
        ),
    ]