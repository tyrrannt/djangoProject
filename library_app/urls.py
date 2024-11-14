from django.urls import path
from . import views

app_name = 'library_app'

urlpatterns = [
    path('', views.index, name='index'),
    path('video/', views.video, name='video'),
    path('help/', views.HelpList.as_view(), name='help_list'),
    path('help/<int:pk>/', views.HelpItem.as_view(), name='help'),
    path('help/<int:pk>/update/', views.HelpItemUpdate.as_view(), name='help_update'),
    path('help/add/', views.HelpItemAdd.as_view(), name='help_add'),
    path('blank/', views.DocumentFormList.as_view(), name='blank_list'),
    path('blank/<int:pk>/', views.DocumentFormItem.as_view(), name='blank'),
    path('blank/<int:pk>/update/', views.DocumentFormUpdate.as_view(), name='blank_update'),
    path('blank/add/', views.DocumentFormAdd.as_view(), name='blank_add'),
    path('submit/', views.submit_poem, name='submit_poem'),
    path('vote/', views.vote, name='vote'),
    path('vote/success/', views.vote_success, name='vote_success'),
    path('results/', views.results, name='results'),
    path('check_session_cookie_secure/', views.check_session_cookie_secure, name='check_session_cookie_secure'),

]
