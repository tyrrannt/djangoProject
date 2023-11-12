# Generated by Django 4.2.1 on 2023-11-11 14:26

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("hrdepartment_app", "0065_documentsjobdescription_parent_document_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="documentsjobdescription",
            name="parent_document",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                to="hrdepartment_app.documentsjobdescription",
                verbose_name="Предшествующий документ",
            ),
        ),
        migrations.AlterField(
            model_name="documentsorder",
            name="parent_document",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                to="hrdepartment_app.documentsorder",
                verbose_name="Предшествующий документ",
            ),
        ),
        migrations.AlterField(
            model_name="instructions",
            name="parent_document",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                to="hrdepartment_app.instructions",
                verbose_name="Предшествующий документ",
            ),
        ),
        migrations.AlterField(
            model_name="provisions",
            name="parent_document",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                to="hrdepartment_app.provisions",
                verbose_name="Предшествующий документ",
            ),
        ),
    ]
