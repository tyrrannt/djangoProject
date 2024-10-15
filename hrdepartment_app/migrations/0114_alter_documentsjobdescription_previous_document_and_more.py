# Generated by Django 5.0.6 on 2024-10-03 14:50

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("hrdepartment_app", "0113_outfitcard_scan_document"),
    ]

    operations = [
        migrations.AlterField(
            model_name="documentsjobdescription",
            name="previous_document",
            field=models.URLField(
                blank=True, verbose_name="Примечание к предшествующему документу"
            ),
        ),
        migrations.AlterField(
            model_name="documentsorder",
            name="previous_document",
            field=models.URLField(
                blank=True, verbose_name="Примечание к предшествующему документу"
            ),
        ),
        migrations.AlterField(
            model_name="guidancedocuments",
            name="previous_document",
            field=models.URLField(
                blank=True, verbose_name="Примечание к предшествующему документу"
            ),
        ),
        migrations.AlterField(
            model_name="instructions",
            name="previous_document",
            field=models.URLField(
                blank=True, verbose_name="Примечание к предшествующему документу"
            ),
        ),
        migrations.AlterField(
            model_name="provisions",
            name="previous_document",
            field=models.URLField(
                blank=True, verbose_name="Примечание к предшествующему документу"
            ),
        ),
    ]