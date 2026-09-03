"""Формы модуля периодического тестирования сотрудников."""

from django import forms
from django.core.exceptions import ValidationError
from django.forms import inlineformset_factory
from django.utils import timezone

from testing_app.models import (
    Question,
    AnswerOption,
    QuestionCategory,
    Testing,
    LectureMaterial,
    VideoLecture,
)


class QuestionImportForm(forms.Form):
    """Форма загрузки файла Excel для импорта вопросов."""

    file = forms.FileField(
        label="Файл с вопросами (.xlsx)",
        help_text="Выберите файл формата Microsoft Excel (.xlsx), заполненный по установленному шаблону.",
        widget=forms.FileInput(attrs={
            "class": "form-control",
            "accept": ".xlsx, application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        })
    )

    def clean_file(self):
        """Проверяет корректность расширения загруженного файла."""
        file = self.cleaned_data.get("file")
        if file:
            filename = file.name.lower()
            if not filename.endswith(".xlsx"):
                raise ValidationError("Разрешены только файлы формата .xlsx (Microsoft Excel).")
        return file


class QuestionCategoryForm(forms.ModelForm):
    """Форма создания и редактирования категории вопросов."""

    class Meta:
        model = QuestionCategory
        fields = ["name", "description", "is_active"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Название категории"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 3, "placeholder": "Описание категории"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }


class QuestionForm(forms.ModelForm):
    """Форма создания и редактирования вопроса."""

    class Meta:
        model = Question
        fields = ["category", "text", "explanation", "status", "difficulty"]
        widgets = {
            "category": forms.Select(attrs={"class": "form-control form-select"}),
            "text": forms.Textarea(attrs={"class": "form-control", "rows": 3, "placeholder": "Формулировка вопроса"}),
            "explanation": forms.Textarea(attrs={"class": "form-control", "rows": 2, "placeholder": "Пояснение к правильному ответу (необязательно)"}),
            "status": forms.Select(attrs={"class": "form-control form-select"}),
            "difficulty": forms.Select(attrs={"class": "form-control form-select"}),
        }


class AnswerOptionForm(forms.ModelForm):
    """Форма варианта ответа."""

    class Meta:
        model = AnswerOption
        fields = ["order_num", "text", "is_correct"]
        widgets = {
            "order_num": forms.HiddenInput(),
            "text": forms.TextInput(attrs={"class": "form-control", "placeholder": "Текст варианта ответа"}),
            "is_correct": forms.CheckboxInput(attrs={"class": "form-check-input correct-answer-radio"}),
        }


AnswerOptionFormSet = inlineformset_factory(
    Question,
    AnswerOption,
    form=AnswerOptionForm,
    extra=4,
    max_num=4,
    can_delete=False
)


class TestingForm(forms.ModelForm):
    """Форма создания и редактирования мероприятия тестирования."""

    order_date = forms.DateField(
        label="Дата приказа",
        widget=forms.DateInput(
            attrs={"class": "form-control", "type": "date"},
            format="%Y-%m-%d"
        ),
        input_formats=["%Y-%m-%d", "%d.%m.%Y"]
    )
    start_datetime = forms.DateTimeField(
        label="Дата и время начала тестирования",
        widget=forms.DateTimeInput(
            attrs={"class": "form-control", "type": "datetime-local"},
            format="%Y-%m-%dT%H:%M"
        ),
        input_formats=[
            "%Y-%m-%dT%H:%M",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%d.%m.%Y %H:%M",
        ]
    )
    end_datetime = forms.DateTimeField(
        label="Дата и время окончания тестирования",
        widget=forms.DateTimeInput(
            attrs={"class": "form-control", "type": "datetime-local"},
            format="%Y-%m-%dT%H:%M"
        ),
        input_formats=[
            "%Y-%m-%dT%H:%M",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%d.%m.%Y %H:%M",
        ]
    )

    class Meta:
        model = Testing
        fields = [
            "title",
            "order_number",
            "order_date",
            "order_name",
            "description",
            "start_datetime",
            "end_datetime",
            "questions_count",
            "passing_score_percentage",
            "max_attempts",
            "attempt_duration_minutes",
            "status",
        ]
        widgets = {
            "title": forms.TextInput(attrs={"class": "form-control", "placeholder": "Периодическая проверка знаний работников"}),
            "order_number": forms.TextInput(attrs={"class": "form-control", "placeholder": "№ 123"}),
            "order_name": forms.TextInput(attrs={"class": "form-control", "placeholder": "О проведении периодической проверки знаний"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 3, "placeholder": "Дополнительная информация к приказу..."}),
            "questions_count": forms.NumberInput(attrs={"class": "form-control", "min": 1}),
            "passing_score_percentage": forms.NumberInput(attrs={"class": "form-control", "min": 1, "max": 100}),
            "max_attempts": forms.NumberInput(attrs={"class": "form-control", "min": 1}),
            "attempt_duration_minutes": forms.NumberInput(attrs={"class": "form-control", "min": 1}),
            "status": forms.Select(attrs={"class": "form-control form-select"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            if self.instance.order_date:
                self.initial["order_date"] = self.instance.order_date.strftime("%Y-%m-%d")
            if self.instance.start_datetime:
                local_start = timezone.localtime(self.instance.start_datetime)
                self.initial["start_datetime"] = local_start.strftime("%Y-%m-%dT%H:%M")
            if self.instance.end_datetime:
                local_end = timezone.localtime(self.instance.end_datetime)
                self.initial["end_datetime"] = local_end.strftime("%Y-%m-%dT%H:%M")

    def clean(self):
        cleaned_data = super().clean()
        start = cleaned_data.get("start_datetime")
        end = cleaned_data.get("end_datetime")
        if start and end and start >= end:
            self.add_error("end_datetime", "Дата и время окончания должны быть строго позже даты начала.")
        return cleaned_data


class GroupPositionsForm(forms.Form):
    """Форма настройки привязки должностей к двум группам тестирования с контролем пересечения."""

    group1_positions = forms.ModelMultipleChoiceField(
        queryset=None,
        required=False,
        label="Должности: Выполняющие работы по обеспечению ТО ВС",
        widget=forms.SelectMultiple(attrs={"class": "form-control select2", "size": "8"})
    )
    group2_positions = forms.ModelMultipleChoiceField(
        queryset=None,
        required=False,
        label="Должности: Выполняющие ТО ВС",
        widget=forms.SelectMultiple(attrs={"class": "form-control select2", "size": "8"})
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from customers_app.models import Job
        job_qs = Job.objects.all().order_by("name")
        self.fields["group1_positions"].queryset = job_qs
        self.fields["group2_positions"].queryset = job_qs

    def clean(self):
        return super().clean()


class ManualAssignmentForm(forms.Form):
    """Форма ручного назначения сотрудника в группу тестирования."""

    group = forms.ModelChoiceField(
        queryset=None,
        label="Группа тестирования",
        widget=forms.Select(attrs={"class": "form-control form-select"})
    )
    employee = forms.ModelChoiceField(
        queryset=None,
        label="Сотрудник",
        widget=forms.Select(attrs={"class": "form-control form-select select2"})
    )

    def __init__(self, testing, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from customers_app.models import DataBaseUser
        self.fields["group"].queryset = testing.groups.all()
        # Исключаем тех, кто уже назначен
        assigned_ids = testing.assignments.values_list("employee_id", flat=True)
        self.fields["employee"].queryset = DataBaseUser.objects.filter(is_active=True).exclude(id__in=assigned_ids).order_by("last_name", "first_name")


class LectureMaterialForm(forms.ModelForm):
    """Форма создания и редактирования лекционного материала."""

    class Meta:
        model = LectureMaterial
        fields = ["title", "doc_file", "scan_file", "is_actual", "description"]
        widgets = {
            "title": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Введите наименование лекции (например: РО-8Т. Раздел 001)"
            }),
            "doc_file": forms.FileInput(attrs={
                "class": "form-control",
                "accept": ".doc,.docx,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            }),
            "scan_file": forms.FileInput(attrs={
                "class": "form-control",
                "accept": ".pdf,application/pdf"
            }),
            "is_actual": forms.CheckboxInput(attrs={
                "class": "form-check-input"
            }),
            "description": forms.Textarea(attrs={
                "class": "form-control",
                "rows": 4,
                "placeholder": "Краткая аннотация, методические указания или содержание лекции..."
            }),
        }

    def clean(self):
        cleaned_data = super().clean()
        doc_file = cleaned_data.get("doc_file")
        scan_file = cleaned_data.get("scan_file")

        # При создании новой лекции желательно прикрепить хотя бы один файл
        if not self.instance.pk and not doc_file and not scan_file:
            raise ValidationError("Необходимо прикрепить хотя бы один файл (скан документа PDF или файл Word doc/docx).")

        return cleaned_data


class VideoLectureForm(forms.ModelForm):
    """Форма создания и редактирования видеолекции."""

    class Meta:
        model = VideoLecture
        fields = ["title", "video_file", "is_actual", "description"]
        widgets = {
            "title": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Введите наименование видеолекции (например: Практическое обслуживание ТВ2-117)"
            }),
            "video_file": forms.FileInput(attrs={
                "class": "form-control",
                "accept": ".mp4,video/mp4"
            }),
            "is_actual": forms.CheckboxInput(attrs={
                "class": "form-check-input"
            }),
            "description": forms.Textarea(attrs={
                "class": "form-control",
                "rows": 4,
                "placeholder": "Краткое описание, таймкоды видео или содержание тем..."
            }),
        }


