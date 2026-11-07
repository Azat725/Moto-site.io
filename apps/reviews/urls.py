from django.urls import path

from . import views

app_name = "reviews"
urlpatterns = [path("submit/", views.submit, name="submit")]
