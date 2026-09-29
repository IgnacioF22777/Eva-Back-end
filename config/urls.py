from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('delegacionesAPP.urls')),
    path('gestion/', include('tubo_gestionAPP.urls')),
]