import logging

from django.conf import settings
from django.http import JsonResponse
from django.views import defaults
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler

logger = logging.getLogger("sgr.api")


# ============================================================
# MANEJO SEGURO DE ERRORES DE LA API
# ============================================================
# Toda respuesta bajo /api/ es JSON, también en los casos que DRF no
# cubre por sí solo:
#
#   - Excepción no controlada dentro de una vista de la API -> 500 JSON
#     con un mensaje genérico. El detalle (traza) se registra en el log
#     del servidor y nunca se envía al cliente, para no exponer rutas,
#     consultas ni datos internos.
#   - Ruta inexistente bajo /api/ -> 404 JSON (antes, página HTML).
#   - Error 500 fuera de una vista DRF bajo /api/ -> 500 JSON.
#
# Fuera de /api/ se mantienen las páginas HTML normales de Django.

MENSAJE_500 = (
    "Error interno del servidor. El incidente quedó registrado; intente "
    "nuevamente o contacte al administrador."
)
MENSAJE_404 = "El recurso solicitado no existe en la API."


def manejador_excepciones(exc, context):
    """EXCEPTION_HANDLER de DRF: lo no controlado responde 500 en JSON."""
    respuesta = exception_handler(exc, context)

    if respuesta is not None:
        return respuesta

    # Con DEBUG=True se deja pasar la excepción para ver la traza local.
    if settings.DEBUG:
        return None

    request = context.get("request")
    logger.exception(
        "Error no controlado en la API: %s %s",
        getattr(request, "method", "?"),
        getattr(request, "path", "?"),
    )
    return Response(
        {"detail": MENSAJE_500}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
    )


def es_api(request):
    return request.path.startswith("/api/")


def pagina_no_encontrada(request, exception):
    """handler404: JSON bajo /api/, página normal en el resto del sitio."""
    if es_api(request):
        return JsonResponse({"detail": MENSAJE_404}, status=404)
    return defaults.page_not_found(request, exception)


def error_servidor(request):
    """handler500: JSON bajo /api/, página normal en el resto del sitio."""
    if es_api(request):
        return JsonResponse({"detail": MENSAJE_500}, status=500)
    return defaults.server_error(request)
