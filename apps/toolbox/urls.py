from django.urls import path

from . import views

app_name = 'toolbox'
urlpatterns = [
    path('', views.home, name='home'),
    path('add/<slug:slug>/', views.add, name='add'),
    path('remove/<slug:slug>/', views.remove, name='remove'),
    path('setting/<slug:slug>/', views.setting, name='setting'),
]
