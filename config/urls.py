
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

    # Proyecto Integrado (Eva 3) - Matriz SGR: ausencias, felicitaciones
    # y reclamos (Camilo)
    path("matriz/", include("matrizAPP.urls")),
    path("regalos/", include("beneficiosAPP.urls")),

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

    # Programación Back End - Emergencias territoriales y reportes
    # ciudadanos (mantenedores y transacción de derivación)
    path("emergencias/", include("emergenciasTerritorialesAPP.urls")),
    path("reportes/", include("reportesCiudadanosAPP.urls")),

    # Proyecto Integrado EVA 3 - Actividades diarias (R1-R5)
    path("actividades/", include("actividadesAPP.urls")),

    # Proyecto Integrado EVA 3 - Puntaje del equipo de la delegación (R10)
    path("puntaje-equipo/", include("puntajeEquipoAPP.urls")),

    # Proyecto Integrado EVA 3 - Alertas de registros sospechosos (R6)
    path("alertas/", include("alertasAPP.urls")),
]
