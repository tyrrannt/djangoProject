# Generated by Django 5.0.6 on 2025-03-21 08:20

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("hrdepartment_app", "0121_placeproductionactivity_work_email_password"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="documentsjobdescription",
            options={
                "ordering": ("-document_date",),
                "verbose_name": "Должностная инструкция",
                "verbose_name_plural": "Должностные инструкции",
            },
        ),
    ]
