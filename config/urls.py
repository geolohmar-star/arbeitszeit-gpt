from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

urlpatterns = [
    path('admin/', admin.site.urls),

    # Authentication
    path('accounts/login/', auth_views.LoginView.as_view(template_name='registration/login.html'), name='login'),
    path('accounts/logout/', auth_views.LogoutView.as_view(next_page='/'), name='logout'),  # ← next_page hinzugefügt!
    path('accounts/', include('django.contrib.auth.urls')),

    # APPS
    path('', include('arbeitszeit.urls')),
    path('schichtplan/', include('schichtplan.urls')),
    path('formulare/', include('formulare.urls')),
    path('berechtigungen/', include('berechtigungen.urls')),
    path('hr/', include('hr.urls')),
    path('workflow/', include('workflow.urls')),
]

# Media-Files (nur in Development)
if settings.DEBUG:
    urlpatterns += static(
        settings.MEDIA_URL,
        document_root=settings.MEDIA_ROOT,
    )