# Generated by Django 4.0.5 on 2022-06-30 14:04

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('customers_app', '0002_alter_databaseuser_age'),
    ]

    operations = [
        migrations.AlterField(
            model_name='databaseuser',
            name='age',
            field=models.PositiveIntegerField(blank=True, default=18, verbose_name='возраст'),
        ),
    ]