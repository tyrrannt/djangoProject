# Generated by Django 4.0.5 on 2022-07-15 06:54

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('customers_app', '0009_remove_databaseuser_works_databaseuser_divisions_and_more'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='databaseuser',
            name='corp_phone',
        ),
        migrations.RemoveField(
            model_name='databaseuser',
            name='phone',
        ),
        migrations.AddField(
            model_name='databaseuser',
            name='internal_phone',
            field=models.CharField(blank=True, max_length=3, null=True, verbose_name='Внутренний номер телефона'),
        ),
        migrations.AddField(
            model_name='databaseuser',
            name='personal_phone',
            field=models.CharField(blank=True, max_length=15, null=True, verbose_name='Личный номер телефона'),
        ),
        migrations.AddField(
            model_name='databaseuser',
            name='work_phone',
            field=models.CharField(blank=True, max_length=15, null=True, verbose_name='Корпоративный номер телефона'),
        ),
        migrations.AlterField(
            model_name='counteragent',
            name='phone',
            field=models.CharField(blank=True, max_length=15, null=True, verbose_name='Корпоративный номер телефона'),
        ),
        migrations.DeleteModel(
            name='PhoneNumber',
        ),
    ]
