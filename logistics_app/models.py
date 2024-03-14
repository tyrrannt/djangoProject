from django.db import models

from customers_app.models import DataBaseUser
from hrdepartment_app.models import PlaceProductionActivity


# Create your models here.

class WayBill(models.Model):
    class Meta:
        verbose_name = "Транспортная накладная"
        verbose_name_plural = "Транспортные накладные"
        ordering = ["-date_of_creation"]

    document_number = models.CharField(max_length=100, verbose_name="Номер документа")
    document_date = models.DateField(verbose_name="Дата документа")
    executor = models.ForeignKey(DataBaseUser, max_length=100, verbose_name="Исполнитель",
                                 on_delete=models.SET_NULL, null=True, blank=True, related_name="way_bill_executor")
    date_of_creation = models.DateField(verbose_name="Дата и время создания", auto_now_add=True)
    place_of_departure = models.ForeignKey(PlaceProductionActivity, verbose_name="Место отправления", on_delete=models.SET_NULL, null=True, blank=True, related_name="way_bill_place_of_departure")

    def __str__(self):
        return self.document_number