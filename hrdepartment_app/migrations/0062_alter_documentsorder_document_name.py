# Generated by Django 4.2.1 on 2023-08-07 13:31

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("hrdepartment_app", "0061_alter_orderdescription_name"),
    ]

    operations = [
        migrations.AlterField(
            model_name="documentsorder",
            name="document_name",
            field=models.ForeignKey(
                blank=True,
                default=None,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                to="hrdepartment_app.orderdescription",
                verbose_name="Наименование документа",
            ),
        ),
    ]
