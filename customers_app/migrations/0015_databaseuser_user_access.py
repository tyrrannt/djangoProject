# Generated by Django 4.1.7 on 2023-03-14 07:10

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('customers_app', '0014_alter_job_group'),
    ]

    operations = [
        migrations.AddField(
            model_name='databaseuser',
            name='user_access',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='customers_app.accesslevel', verbose_name='Права доступа'),
        ),
    ]
