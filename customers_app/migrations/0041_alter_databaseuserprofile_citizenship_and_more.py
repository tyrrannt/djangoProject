# Generated by Django 4.1 on 2022-08-27 15:59

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('customers_app', '0040_alter_counteragent_ogrn'),
    ]

    operations = [
        migrations.AlterField(
            model_name='databaseuserprofile',
            name='citizenship',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='customers_app.citizenships', verbose_name='Гражданство'),
        ),
        migrations.AlterField(
            model_name='databaseuserprofile',
            name='passport',
            field=models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='customers_app.identitydocuments', verbose_name='Паспорт'),
        ),
    ]