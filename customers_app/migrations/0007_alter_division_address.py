# Generated by Django 4.1.6 on 2023-02-22 09:51

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('customers_app', '0006_databaseuser_service_number'),
    ]

    operations = [
        migrations.AlterField(
            model_name='division',
            name='address',
            field=models.CharField(blank=True, default='', max_length=250, verbose_name='Адрес'),
        ),
    ]
