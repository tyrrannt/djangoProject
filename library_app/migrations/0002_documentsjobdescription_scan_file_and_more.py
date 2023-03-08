# Generated by Django 4.1.7 on 2023-03-07 12:06

from django.db import migrations, models
import library_app.models


class Migration(migrations.Migration):

    dependencies = [
        ('library_app', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='documentsjobdescription',
            name='scan_file',
            field=models.FileField(blank=True, upload_to=library_app.models.jds_directory_path, verbose_name='Скан документа'),
        ),
        migrations.AddField(
            model_name='documentsorder',
            name='scan_file',
            field=models.FileField(blank=True, upload_to=library_app.models.ord_directory_path, verbose_name='Скан документа'),
        ),
    ]
