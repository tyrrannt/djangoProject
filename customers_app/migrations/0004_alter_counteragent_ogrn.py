# Generated by Django 4.1.5 on 2023-01-05 11:47

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('customers_app', '0003_alter_harmfulworkingconditions_code'),
    ]

    operations = [
        migrations.AlterField(
            model_name='counteragent',
            name='ogrn',
            field=models.CharField(blank=True, default='', max_length=15, verbose_name='ОГРН'),
        ),
    ]