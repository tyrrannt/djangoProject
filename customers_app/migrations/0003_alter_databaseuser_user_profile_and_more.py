# Generated by Django 4.1.6 on 2023-02-22 08:36

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ('customers_app', '0002_databaseuserworkprofile_ref_key'),
    ]

    operations = [
        migrations.AlterField(
            model_name='databaseuser',
            name='user_profile',
            field=models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE,
                                       to='customers_app.databaseuserprofile',
                                       verbose_name='Личный профиль пользователя'),
        ),
        migrations.AlterField(
            model_name='databaseuser',
            name='user_work_profile',
            field=models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE,
                                       to='customers_app.databaseuserworkprofile',
                                       verbose_name='Рабочий профиль пользователя'),
        ),
    ]
