from django.db import models

from customers_app.models import DataBaseUser, Division
from hrdepartment_app.models import PlaceProductionActivity


# Create your models here.

class WayBill(models.Model):
    class Meta:
        verbose_name = "Транспортная накладная"
        verbose_name_plural = "Транспортные накладные"
        ordering = ["-date_of_creation"]

    STATES = (
        (0, "Не обработана"),
        (1, "Обработана"),
        (2, "Отправлена"),
        (3, "Принята"),
        (4, "Отклонена"),
    )

    document_number = models.CharField(max_length=100, verbose_name="Номер документа", )
    document_date = models.DateField(verbose_name="Дата документа")
    executor = models.ForeignKey(DataBaseUser, max_length=100, verbose_name="Исполнитель",
                                 on_delete=models.SET_NULL, null=True, blank=True, related_name="way_bill_executor")
    date_of_creation = models.DateField(verbose_name="Дата и время создания",
                                        auto_now_add=True)  # При миграции указать 1 и вставить timezone.now()
    place_of_departure = models.ForeignKey(PlaceProductionActivity, verbose_name="Куда",
                                           on_delete=models.SET_NULL, null=True, blank=True,
                                           related_name="way_bill_place_of_departure")
    place_division = models.ForeignKey(Division, verbose_name="Подразделение", on_delete=models.SET_NULL,
                                       null=True, blank=True)
    comment = models.TextField(verbose_name="Комментарий", blank=True, null=True)
    state = models.CharField(max_length=100, verbose_name="Состояние", choices=STATES, default=0)

    def __str__(self):
        return self.document_number
