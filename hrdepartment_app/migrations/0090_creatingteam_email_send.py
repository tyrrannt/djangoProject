# Generated by Django 5.0.3 on 2024-04-11 11:59

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        (
            "hrdepartment_app",
            "0089_alter_creatingteam_options_alter_reportcard_options",
        ),
    ]

    operations = [
        migrations.AddField(
            model_name="creatingteam",
            name="email_send",
            field=models.BooleanField(default=False, verbose_name="Письмо отправлено"),
        ),
    ]
