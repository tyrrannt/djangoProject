# Generated by Django 4.2.1 on 2023-06-17 12:04

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('hrdepartment_app', '0052_documentsjobdescription_applying_for_job_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='documentsjobdescription',
            name='document_number',
            field=models.CharField(default='', max_length=18, verbose_name='Номер документа'),
        ),
        migrations.AlterField(
            model_name='documentsorder',
            name='document_number',
            field=models.CharField(default='', max_length=18, verbose_name='Номер документа'),
        ),
    ]