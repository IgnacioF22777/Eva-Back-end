from django.urls import include, path


# ============================================================
# RUTAS DEL SGR
# ============================================================
# La Evaluación Sumativa #3 prohíbe usar Django Admin como
# mecanismo de administración. Por eso /admin/ no se expone:
# toda operación se realiza desde las interfaces propias
# desarrolladas con Django Templates.
#
# Las apps de Django Admin siguen instaladas porque el modelo
# de usuarios y grupos las utiliza internamente, pero su panel
# no está disponible para ningún perfil.

urlpatterns = [
    path("", include("delegacionesAPP.urls")),
    path("gestion/", include("tubo_gestionAPP.urls")),

    # Proyecto Integrado - CRUD de tablas maestras
    path("maestros/", include("sgr_maestrosAPP.urls")),

    # Proyecto Integrado - Seguridad: login, usuarios y roles
    path("seguridad/", include("seguridadAPP.urls")),
]
