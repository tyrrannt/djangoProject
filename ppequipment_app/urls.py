from django.urls import path
from . import views

app_name = 'ppequipment_app'

urlpatterns = [
    path('', views.equipment_list, name='index'),

    # Оборудование
    path('equipment/', views.equipment_list, name='equipment_list'),
    path('equipment/create/', views.equipment_create, name='equipment_create'),
    path('equipment/<int:pk>/', views.equipment_detail, name='equipment_detail'),
    path('equipment/<int:pk>/update/', views.equipment_update, name='equipment_update'),
    path('equipment/<int:pk>/delete/', views.equipment_delete, name='equipment_delete'),

    # Сверки
    path('verifications/', views.verification_list, name='verification_list'),
    path('verifications/create/', views.verification_create, name='verification_create'),
    path('verifications/<slug:slug>/', views.verification_detail, name='verification_detail'),
    path('verifications/<slug:slug>/update/', views.verification_update, name='verification_update'),
    path('verifications/<slug:slug>/delete/', views.verification_delete, name='verification_delete'),

    # Местоположения
    path('locations/', views.location_list, name='location_list'),
    path('locations/create/', views.location_create, name='location_create'),
    path('locations/<int:pk>/update/', views.location_update, name='location_update'),
    path('locations/<int:pk>/delete/', views.location_delete, name='location_delete'),

    # Даты сверок
    path('verification-dates/', views.verification_date_list, name='verification_date_list'),
    path('verification-dates/create/', views.verification_date_create, name='verification_date_create'),
    path('verification-dates/<int:pk>/update/', views.verification_date_update, name='verification_date_update'),
    path('verification-dates/<int:pk>/delete/', views.verification_date_delete, name='verification_date_delete'),

    # Справочники
    path('refs/dest-lit/', views.dest_lit_list, name='dest_lit_list'),
    path('refs/dest-lit/create/', views.dest_lit_create, name='dest_lit_create'),
    path('refs/dest-lit/<int:pk>/update/', views.dest_lit_update, name='dest_lit_update'),
    path('refs/dest-lit/<int:pk>/delete/', views.dest_lit_delete, name='dest_lit_delete'),

    path('refs/locations/', views.location_ref_list, name='location_ref_list'),
    path('refs/locations/create/', views.location_ref_create, name='location_ref_create'),
    path('refs/locations/<int:pk>/update/', views.location_ref_update, name='location_ref_update'),
    path('refs/locations/<int:pk>/delete/', views.location_ref_delete, name='location_ref_delete'),

    path('refs/aircraft-types/', views.aircraft_type_list, name='aircraft_type_list'),
    path('refs/aircraft-types/create/', views.aircraft_type_create, name='aircraft_type_create'),
    path('refs/aircraft-types/<int:pk>/update/', views.aircraft_type_update, name='aircraft_type_update'),
    path('refs/aircraft-types/<int:pk>/delete/', views.aircraft_type_delete, name='aircraft_type_delete'),

    path('refs/contractor-status/', views.contractor_status_list, name='contractor_status_list'),
    path('refs/contractor-status/create/', views.contractor_status_create, name='contractor_status_create'),
    path('refs/contractor-status/<int:pk>/update/', views.contractor_status_update, name='contractor_status_update'),
    path('refs/contractor-status/<int:pk>/delete/', views.contractor_status_delete, name='contractor_status_delete'),

    # Импорт
    path('import-mdb/', views.import_from_mdb, name='import_mdb'),

    # Свёрочные этикетки
    path('verification-labels/', views.verification_labels, name='verification_labels'),

    # QR-код для этикетки
    path('qr/<slug:slug>/', views.generate_verification_qr, name='verification_qr'),
]
