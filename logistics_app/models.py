import uuid

from django.db import models

from administration_app.utils import format_name_initials
from customers_app.models import DataBaseUser, Division
from hrdepartment_app.models import PlaceProductionActivity


# Create your models here.

class WayBill(models.Model):
    class Meta:
        verbose_name = "Транспортная накладная"
        verbose_name_plural = "Транспортные накладные"
        ordering = ["-date_of_creation"]

    STATES = (
        ("0", "Не обработана"),
        ("1", "Обработана"),
        ('2', "Отправлена"),
        ("3", "Принята"),
        ("4", "Отклонена"),
    )

    URGENCY_CHOICES = (
        ("0", "Не срочно"),
        ("1", "Срочно"),
        ("2", "Очень срочно"),
    )

    document_number = models.CharField(max_length=37, verbose_name="Номер документа", default=uuid.uuid4)
    document_date = models.DateField(verbose_name="Дата документа")
    place_of_departure = models.ForeignKey(PlaceProductionActivity, verbose_name="Куда",
                                           on_delete=models.SET_NULL, null=True, blank=True,
                                           related_name="way_bill_place_of_departure")
    content = models.TextField(verbose_name="Содержание", default='')
    comment = models.CharField(verbose_name="Комментарий", default='', max_length=300)
    place_division = models.ForeignKey(Division, verbose_name="Подразделение", on_delete=models.SET_NULL,
                                       null=True, blank=True)
    sender = models.ForeignKey(DataBaseUser, max_length=100, verbose_name="Отправитель",
                                 on_delete=models.SET_NULL, null=True, blank=True, related_name="way_bill_sender")
    state = models.CharField(max_length=100, verbose_name="Состояние", choices=STATES, default="0")
    responsible = models.ForeignKey(DataBaseUser, max_length=100, verbose_name="Получение",
                                 on_delete=models.SET_NULL, null=True, blank=True, related_name="way_bill_responsible")
    date_of_creation = models.DateField(verbose_name="Дата и время создания",
                                        auto_now_add=True)  # При миграции указать 1 и вставить timezone.now()
    executor = models.ForeignKey(DataBaseUser, max_length=100, verbose_name="Исполнитель",
                                 on_delete=models.SET_NULL, null=True, blank=True, related_name="way_bill_executor")
    urgency = models.CharField(max_length=100, verbose_name="Срочность", choices=URGENCY_CHOICES, default="0")
    package_number = models.ForeignKey('Package', verbose_name="Посылка", on_delete=models.SET_NULL, null=True, blank=True)
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
            "sender": format_name_initials(self.sender.title),
            "state": self.get_state_display(),
            "responsible": format_name_initials(self.responsible.title),
            "date_of_creation": f"{self.date_of_creation:%d.%m.%Y} г.",
            "executor": format_name_initials(self.executor.title),
            "urgency": self.get_urgency_display(),
        }


class Package(models.Model):
    class Meta:
        verbose_name = 'Посылка'
        verbose_name_plural = 'Посылки'
        ordering = ["-date_of_creation"]

    date_of_creation = models.DateField(verbose_name='Дата и время создания', auto_now_add=True) # При миграции указать 1 и вставить timezone.now()
    date_of_dispatch = models.DateField(verbose_name='Дата отправки', null=True, blank=True)
    place_of_dispatch = models.ForeignKey(PlaceProductionActivity, verbose_name='Куда отправляется', on_delete=models.SET_NULL, null=True, blank=True)
    number_of_dispatch = models.CharField(verbose_name='Номер посылки', max_length=37, default='')