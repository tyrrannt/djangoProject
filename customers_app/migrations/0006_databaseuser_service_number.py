# Generated by Django 4.1.6 on 2023-02-22 08:47

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('customers_app', '0005_remove_databaseuserworkprofile_service_number'),
    ]

    operations = [
        migrations.AddField(
            model_name='databaseuser',
            name='service_number',
            field=models.CharField(blank=True, default='', max_length=10, verbose_name='Табельный номер'),
        ),
    ]
