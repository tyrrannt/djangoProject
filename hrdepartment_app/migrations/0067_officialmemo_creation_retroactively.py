# Generated by Django 4.2.1 on 2023-11-29 20:31

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        (
            "hrdepartment_app",
            "0066_alter_documentsjobdescription_parent_document_and_more",
        ),
    ]

    operations = [
        migrations.AddField(
            model_name="officialmemo",
            name="creation_retroactively",
            field=models.BooleanField(
                default=False, verbose_name="Документ введен задним числом"
            ),
        ),
    ]
