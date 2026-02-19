from django.urls import path
from . import views

app_name = "hr"

urlpatterns = [
    path("", views.mitarbeiter_liste, name="liste"),
    path("organigramm/", views.organigramm, name="organigramm"),
    path("<int:pk>/", views.mitarbeiter_detail, name="detail"),
]
