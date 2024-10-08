# Generated by Django 5.0.6 on 2024-09-18 14:48

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("hrdepartment_app", "0105_reportcard_additional_work_reportcard_other_work"),
    ]

    operations = [
        migrations.AlterField(
            model_name="periodicwork",
            name="ratio",
            field=models.FloatField(blank=True, verbose_name="Норма-часы"),
        ),
        migrations.RemoveField(
            model_name="reportcard",
            name="operational_work",
        ),
        migrations.RemoveField(
            model_name="reportcard",
            name="periodic_work",
        ),
        migrations.AddField(
            model_name="reportcard",
            name="operational_work",
            field=models.ManyToManyField(
                related_name="report_operational",
                to="hrdepartment_app.operationalwork",
                verbose_name="Оперативные работы",
            ),
        ),
        migrations.AddField(
            model_name="reportcard",
            name="periodic_work",
            field=models.ManyToManyField(
                related_name="report_periodic",
                to="hrdepartment_app.periodicwork",
                verbose_name="Периодические работы",
            ),
        ),
    ]
