from django.urls import path
from . import views

app_name = "datensicherung"

urlpatterns = [
    path("", views.uebersicht, name="uebersicht"),
    path("backup/", views.backup_ausloesen, name="backup_ausloesen"),
    path("restore-test/", views.restore_test_ausloesen, name="restore_test_ausloesen"),
    path("status/", views.status_partial, name="status_partial"),
]
