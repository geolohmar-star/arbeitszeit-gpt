from django.urls import path
from . import views

app_name = "signatur"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("zertifikate/", views.zertifikat_liste, name="zertifikat_liste"),
    path("zertifikate/<int:pk>/sperren/", views.zertifikat_sperren, name="zertifikat_sperren"),
    path("protokoll/<int:pk>/", views.protokoll_detail, name="protokoll_detail"),
    path("protokoll/<int:pk>/download/", views.pdf_download, name="pdf_download"),
    path("dokumentation.pdf", views.dokumentation_pdf, name="dokumentation_pdf"),
]
