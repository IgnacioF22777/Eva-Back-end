"""Contraseña temporal: cambio obligatorio en el primer ingreso (Eva 3).

Cuando el administrador crea un usuario o le restablece la contraseña,
esa contraseña es temporal (PerfilUsuario.debe_cambiar_password). Mientras
no la cambie, cualquier página lo redirige al formulario de cambio; solo
puede cerrar sesión o cargar archivos estáticos.

La API (JWT) no pasa por la sesión web y no se ve afectada.
"""

from django.conf import settings
from django.shortcuts import redirect
from django.urls import reverse


class CambioPasswordObligatorioMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        usuario = getattr(request, "user", None)
        if usuario is not None and usuario.is_authenticated and self.debe_cambiar(usuario):
            permitidas = (
                reverse("seguridad:cambiar_password"),
                reverse("seguridad:logout"),
            )
            ruta = request.path
            estaticos = settings.STATIC_URL or "/static/"
            if ruta not in permitidas and not ruta.startswith(estaticos):
                return redirect("seguridad:cambiar_password")
        return self.get_response(request)

    @staticmethod
    def debe_cambiar(usuario):
        try:
            return usuario.perfil.debe_cambiar_password
        except Exception:  # sin perfil (p. ej. superusuario creado por consola)
            return False
