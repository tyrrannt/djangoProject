# Generated by Django 4.2 on 2023-05-04 19:00

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('hrdepartment_app', '0024_officialmemo_cancellation_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='approvaloficialmemoprocess',
            name='originals_received',
            field=models.BooleanField(default=False, verbose_name='Получены оригиналы'),
        ),
        migrations.AddField(
            model_name='approvaloficialmemoprocess',
            name='person_clerk',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='person_clerk', to=settings.AUTH_USER_MODEL, verbose_name='Делопроизводитель'),
        ),
        migrations.AlterField(
            model_name='approvaloficialmemoprocess',
            name='process_accepted',
            field=models.BooleanField(default=False, verbose_name='Издан приказ'),
        ),
    ]
