# Generated by Django 4.1.3 on 2022-11-23 16:10

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ('hrdepartment_app', '0012_alter_approvaloficialmemoprocess_document'),
    ]

    operations = [
        migrations.AlterField(
            model_name='approvaloficialmemoprocess',
            name='document',
            field=models.OneToOneField(null=True, on_delete=django.db.models.deletion.CASCADE,
                                       to='hrdepartment_app.officialmemo', verbose_name='Документ'),
        ),
    ]
