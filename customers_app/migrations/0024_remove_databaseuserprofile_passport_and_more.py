# Generated by Django 4.1.7 on 2023-03-14 17:26

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('customers_app', '0023_alter_databaseuserprofile_passport'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='databaseuserprofile',
            name='passport',
        ),
        migrations.AddField(
            model_name='databaseuserprofile',
            name='passport',
            field=models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='customers_app.identitydocuments', verbose_name='Паспорт'),
        ),
    ]
