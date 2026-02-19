from django.urls import path
from . import views

app_name = "berechtigungen"

urlpatterns = [
    path("", views.uebersicht, name="uebersicht"),
    path("<int:pk>/", views.mitarbeiter_detail, name="detail"),
    path("<int:pk>/vergeben/", views.permission_vergeben, name="vergeben"),
    path("<int:pk>/entziehen/", views.permission_entziehen, name="entziehen"),
    path("protokoll/", views.protokoll, name="protokoll"),
]
