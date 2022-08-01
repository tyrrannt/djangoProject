# Generated by Django 4.0.6 on 2022-07-26 19:41

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('customers_app', '0018_alter_accesslevel_name'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='databaseuser',
            name='access_right',
        ),
        migrations.AddField(
            model_name='databaseuser',
            name='access_right',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='customers_app.accesslevel', verbose_name='права доступа'),
        ),
    ]