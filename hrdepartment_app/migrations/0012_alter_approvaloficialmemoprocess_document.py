# Generated by Django 4.1.3 on 2022-11-23 14:01

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ('hrdepartment_app', '0011_approvaloficialmemoprocess_location_selected'),
    ]

    operations = [
        migrations.AlterField(
            model_name='approvaloficialmemoprocess',
            name='document',
            field=models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, parent_link=True,
                                       to='hrdepartment_app.officialmemo', verbose_name='Документ'),
        ),
    ]
