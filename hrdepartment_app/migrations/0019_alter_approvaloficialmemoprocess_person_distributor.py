# Generated by Django 4.2 on 2023-05-02 21:09

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('hrdepartment_app', '0018_alter_placeproductionactivity_short_name'),
    ]

    operations = [
        migrations.AlterField(
            model_name='approvaloficialmemoprocess',
            name='person_distributor',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='person_distributor', to=settings.AUTH_USER_MODEL, verbose_name='Сотрудник НО'),
        ),
    ]
