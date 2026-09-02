"""Маршруты URL модуля периодического тестирования сотрудников."""

from django.urls import path
from testing_app import views

app_name = "testing_app"

urlpatterns = [
    # Главная и кабинеты
    path("", views.TestingIndexView.as_view(), name="index"),
    path("my/", views.MyTestsView.as_view(), name="my_tests"),
    path("dashboard/", views.ManagerDashboardView.as_view(), name="dashboard"),

    # Банк вопросов и категории (Этап 2)
    path("questions/", views.QuestionBankListView.as_view(), name="questions_bank"),
    path("questions/create/", views.QuestionCreateView.as_view(), name="question_create"),
    path("questions/<int:pk>/edit/", views.QuestionUpdateView.as_view(), name="question_update"),
    path("questions/<int:pk>/toggle-archive/", views.QuestionToggleArchiveView.as_view(), name="question_toggle_archive"),
    path("questions/template/download/", views.QuestionTemplateDownloadView.as_view(), name="question_template_download"),
    path("questions/import/", views.QuestionImportView.as_view(), name="questions_import"),

    # Категории
    path("categories/", views.QuestionCategoryListView.as_view(), name="categories_list"),
    path("categories/create/", views.QuestionCategoryCreateView.as_view(), name="category_create"),
    path("categories/<int:pk>/edit/", views.QuestionCategoryUpdateView.as_view(), name="category_update"),

    # Мероприятия тестирования и группы (Этап 3)
    path("events/", views.TestingEventListView.as_view(), name="event_list"),
    path("events/create/", views.TestingEventCreateView.as_view(), name="event_create"),
    path("events/<int:pk>/", views.TestingEventDetailView.as_view(), name="event_detail"),
    path("events/<int:pk>/edit/", views.TestingEventUpdateView.as_view(), name="event_update"),
    path("events/<int:pk>/positions/", views.TestingEventPositionsUpdateView.as_view(), name="event_positions_update"),
    path("events/<int:pk>/categories/", views.TestingEventCategoriesUpdateView.as_view(), name="event_categories_update"),
    path("events/<int:pk>/manual-assign/", views.TestingEventManualAssignView.as_view(), name="event_manual_assign"),
    path("events/<int:pk>/remove-assign/<int:assign_id>/", views.TestingEventRemoveAssignView.as_view(), name="event_remove_assign"),
    path("events/<int:pk>/change-status/", views.TestingEventStatusChangeView.as_view(), name="event_status_change"),

    # Движок тестирования и прохождение теста (Этап 4)
    path("assignment/<int:assignment_id>/start/", views.StartTestAttemptView.as_view(), name="start_attempt"),
    path("attempt/<int:attempt_id>/", views.TestSessionView.as_view(), name="test_session"),
    path("attempt/<int:attempt_id>/save-answer/", views.SaveDraftAnswerAjaxView.as_view(), name="save_draft_answer"),
    path("attempt/<int:attempt_id>/finish/", views.FinishTestAttemptView.as_view(), name="finish_attempt"),
    path("attempt/<int:attempt_id>/result/", views.TestAttemptResultView.as_view(), name="test_result"),

    # Сертификаты и экзаменационные листы (Этап 5)
    path("attempt/<int:attempt_id>/certificate/", views.CertificateView.as_view(), name="certificate_view"),
    path("attempt/<int:attempt_id>/sheet/", views.AttemptTestSheetView.as_view(), name="attempt_test_sheet"),
    path("verify/<uuid:certificate_uuid>/", views.CertificateVerifyView.as_view(), name="certificate_verify"),

    # Онлайн-мониторинг и экспорт протоколов (Этап 6)
    path("dashboard/live-sessions/", views.LiveMonitoringAjaxView.as_view(), name="dashboard_live_sessions"),
    path("events/<int:pk>/export/excel/", views.TestingProtocolExcelExportView.as_view(), name="event_export_excel"),
    path("events/<int:pk>/export/csv/", views.TestingProtocolCsvExportView.as_view(), name="event_export_csv"),
]
