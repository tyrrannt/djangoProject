# Generated by Django 4.1.5 on 2023-01-29 12:37

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('customers_app', '0004_alter_counteragent_ogrn'),
        ('hrdepartment_app', '0019_remove_officialmemo_place_production_activity_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='officialmemo',
            name='place_production_activity',
            field=models.ManyToManyField(to='customers_app.division', verbose_name='МПД'),
        ),
    ]
