# Generated by Django 4.1.5 on 2023-02-02 12:46

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('customers_app', '0005_databaseuser_person_ref_key'),
    ]

    operations = [
        migrations.AlterField(
            model_name='databaseuser',
            name='person_ref_key',
            field=models.CharField(default='', max_length=37, verbose_name='Уникальный номер физ лица'),
        ),
    ]
