from django.urls import path

from . import views

app_name = 'trajectory'
urlpatterns = [path('', views.mine, name='mine')]
