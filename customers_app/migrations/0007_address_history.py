# Generated by Django 4.0.5 on 2022-07-14 14:33

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('customers_app', '0006_alter_databaseuser_access_right_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='address',
            name='history',
            field=models.DateField(auto_created=True, null=True, verbose_name='Дата создания'),
        ),
    ]
