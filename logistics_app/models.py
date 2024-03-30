import uuid

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

    document_number = models.CharField(max_length=37, verbose_name="Номер документа", default=uuid.uuid4)
    document_date = models.DateField(verbose_name="Дата документа")
    place_of_departure = models.ForeignKey(PlaceProductionActivity, verbose_name="Куда",
                                           on_delete=models.SET_NULL, null=True, blank=True,
                                           related_name="way_bill_place_of_departure")
    content = models.CharField(verbose_name="Содержание", default='', max_length=300)
    comment = models.TextField(verbose_name="Комментарий", blank=True, null=True)
    place_division = models.ForeignKey(Division, verbose_name="Подразделение", on_delete=models.SET_NULL,
                                       null=True, blank=True)
    sender = models.ForeignKey(DataBaseUser, max_length=100, verbose_name="Отправитель",
                                 on_delete=models.SET_NULL, null=True, blank=True, related_name="way_bill_sender")
    state = models.CharField(max_length=100, verbose_name="Состояние", choices=STATES, default=0)
    responsible = models.ForeignKey(DataBaseUser, max_length=100, verbose_name="Получение",
                                 on_delete=models.SET_NULL, null=True, blank=True, related_name="way_bill_responsible")
    date_of_creation = models.DateField(verbose_name="Дата и время создания",
                                        auto_now_add=True)  # При миграции указать 1 и вставить timezone.now()
    executor = models.ForeignKey(DataBaseUser, max_length=100, verbose_name="Исполнитель",
                                 on_delete=models.SET_NULL, null=True, blank=True, related_name="way_bill_executor")

    def __str__(self):
        return self.content

    def get_data(self):
        """
        Получает данные из экземпляра ReportCard.

        :return: словарь, содержащий следующие данные:
            - "pk": первичный ключ экземпляра ReportCard.
            - "employee": форматированные инициалы имени сотрудника.
            - "report_card_day": день табеля в формате "ДД.ММ.ГГГГ"
            - "start_time": время начала в формате "ЧЧ:ММ"
            - "end_time": время окончания в формате "ЧЧ:ММ"
            - "reason_adjustment": причина корректировки.
            - "record_type": отображение типа записи.
        """
        return {
            "pk": self.pk,
            "document_date": f"{self.document_date:%d.%m.%Y} г.",
            "place_of_departure": self.place_of_departure.name,
            "content": self.content,
            "comment": self.comment,
            "place_division": self.place_division.name,
            "sender": self.sender.title,
            "state": self.state,
            "responsible": self.responsible.title,
            "date_of_creation": f"{self.date_of_creation:%d.%m.%Y} г.",
            "executor": self.executor.title,
        }
