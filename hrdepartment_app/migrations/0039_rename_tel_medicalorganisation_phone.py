# Generated by Django 4.1.6 on 2023-02-20 21:08

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('hrdepartment_app', '0038_medicalorganisation_email_medicalorganisation_tel'),
    ]

    operations = [
        migrations.RenameField(
            model_name='medicalorganisation',
            old_name='tel',
            new_name='phone',
        ),
    ]
