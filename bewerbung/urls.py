from django.urls import path

from . import views

app_name = "bewerbung"

urlpatterns = [
    # Bewerber-Seite (kein Login)
    path("neu/", views.bewerbung_erfassen, name="erfassen"),
    path("neu/<int:pk>/dokumente/", views.bewerbung_dokumente, name="erfassen_dokumente"),
    path("danke/", views.bewerbung_danke, name="danke"),

    # HR-Bereich (Login + HR-Recht)
    path("hr/", views.hr_liste, name="hr_liste"),
    path("hr/<int:pk>/", views.hr_detail, name="hr_detail"),
    path("hr/<int:pk>/speichern/", views.hr_detail_speichern, name="hr_detail_speichern"),
    path("hr/<int:pk>/einstellen/", views.hr_einstellen, name="hr_einstellen"),
    path("hr/<int:pk>/ablehnen/", views.hr_ablehnen, name="hr_ablehnen"),
    path("hr/<int:pk>/dokument/<int:dok_pk>/", views.hr_dokument_download, name="hr_dokument_download"),
]
