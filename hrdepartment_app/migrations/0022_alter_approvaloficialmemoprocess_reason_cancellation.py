# Generated by Django 4.2 on 2023-05-04 08:49

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('hrdepartment_app', '0021_alter_officialmemo_document_extension'),
    ]

    operations = [
        migrations.AlterField(
            model_name='approvaloficialmemoprocess',
            name='reason_cancellation',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='hrdepartment_app.reasonforcancellation', verbose_name='Причина отмены'),
        ),
    ]
