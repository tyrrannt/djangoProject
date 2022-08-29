# Generated by Django 4.1 on 2022-08-29 07:52

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('customers_app', '0041_alter_databaseuserprofile_citizenship_and_more'),
        ('hrdepartment_app', '0003_alter_medical_options_medical_harmful'),
    ]

    operations = [
        migrations.AlterField(
            model_name='medical',
            name='harmful',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to='customers_app.harmfulworkingconditions', verbose_name='Вредные условия труда'),
        ),
    ]