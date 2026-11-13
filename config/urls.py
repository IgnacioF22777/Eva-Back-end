
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

    # Proyecto Integrado (Eva 3) - Organizaciones comunitarias y JJVV
    path("organizaciones/", include("organizacionesAPP.urls")),

    # Proyecto Integrado (Eva 3) - Tubo de cartas de Oficina de Partes
    path("oficina-partes/", include("oficinaPartesAPP.urls")),

    # Proyecto Integrado EVA 3 - Tipos de atención social (RC-05)
    path("atencion-social/", include("atencionSocialAPP.urls")),

    # Programación Back End - API RESTful (JWT, Swagger y ReDoc)
    path("api/", include("apiAPP.urls")),

    # Proyecto Integrado EVA 3 - Actividades diarias (R1-R5)
    path("actividades/", include("actividadesAPP.urls")),
]
