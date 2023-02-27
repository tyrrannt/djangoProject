# Generated by Django 4.1.6 on 2023-02-23 17:04

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('hrdepartment_app', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='medicalorganisation',
            name='email',
            field=models.EmailField(default='', max_length=254, verbose_name='Email'),
        ),
        migrations.AlterField(
            model_name='medicalorganisation',
            name='phone',
            field=models.CharField(default='', max_length=15, verbose_name='Телефон'),
        ),
    ]
