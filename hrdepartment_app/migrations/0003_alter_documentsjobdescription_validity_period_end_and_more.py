# Generated by Django 4.1.7 on 2023-03-24 07:04

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('hrdepartment_app', '0002_placeproductionactivity_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='documentsjobdescription',
            name='validity_period_end',
            field=models.DateField(blank=True, default='', verbose_name='Документ действует по'),
        ),
        migrations.AlterField(
            model_name='documentsjobdescription',
            name='validity_period_start',
            field=models.DateField(blank=True, default='', verbose_name='Документ действует с'),
        ),
        migrations.AlterField(
            model_name='documentsorder',
            name='validity_period_end',
            field=models.DateField(blank=True, default='', verbose_name='Документ действует по'),
        ),
        migrations.AlterField(
            model_name='documentsorder',
            name='validity_period_start',
            field=models.DateField(blank=True, default='', verbose_name='Документ действует с'),
        ),
    ]