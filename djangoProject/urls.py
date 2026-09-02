"""djangoProject URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/4.0/topics/http/urls/
"""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.http import JsonResponse
from django.urls import path, include
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerView

from django.views.generic import TemplateView

import library_app.views as library_views

handler403 = library_views.show_403
handler404 = library_views.show_404
handler500 = library_views.show_500

urlpatterns = [
    # PWA Service Worker & Offline Fallback
    path('sw.js', TemplateView.as_view(
        template_name='customers_app/sw.js',
        content_type='application/javascript'
    ), name='service_worker'),
    path('offline/', TemplateView.as_view(
        template_name='customers_app/offline.html'
    ), name='pwa_offline'),

    # Chrome DevTools workspace probe handler
    path('.well-known/appspecific/com.chrome.devtools.json', lambda request: JsonResponse({})),

    path('', include('library_app.urls')),
    path('bklproxmoxadmin/', admin.site.urls),

    # API Schema & UI
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/schema/swagger-ui/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/schema/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),

    path('users/', include('customers_app.urls')),
    path('contracts/', include('contracts_app.urls')),
    path('hr/', include('hrdepartment_app.urls')),
    path('logistics/', include('logistics_app.urls')),
    path('chat/', include('chat_app.urls')),
    path('api/chat/', include('chat_app.api_urls')),
    path('portal/', include('administration_app.urls')),
    path('mirage/', include('telegram_app.urls')),
    path('tasks/', include('tasks_app.urls')),
    path('tickets/', include('tickets_app.urls')),
    path('api/', include('tickets_app.api_urls')),
    path('equipment/', include('ppequipment_app.urls')),
    path('pass/', include('password_manager.urls')),
    path('api/passwords/', include('password_manager.api_urls')),
    path('map/', include('map_viewer.urls')),
    path('api/maps/', include('map_viewer.api_urls')),
    path('flight/', include('flight_planning.urls')),
    path('finance/', include('finance_app.urls')),
    path('api/finance/', include('finance_app.api_urls')),
    path('mail/', include('mailbox_app.urls')),
    path('testing/', include('testing_app.urls')),
    path('ckeditor5/', include('django_ckeditor_5.urls'), name="ck_editor_5_upload_file"),
    path('__debug__/', include('debug_toolbar.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
