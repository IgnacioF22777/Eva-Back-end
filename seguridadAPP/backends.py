from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend

from .models import normalizar_rut


# ============================================================
# BACKEND DE AUTENTICACIÓN: RUT O CORREO + CONTRASEÑA
# ============================================================

class RutOCorreoBackend(ModelBackend):
    """
    Permite iniciar sesión con el RUT o con el correo electrónico.

    - Si el identificador contiene '@' se busca por correo.
    - Si no, se busca por RUT (con o sin puntos y guion).
    - Como respaldo se acepta el nombre de usuario (ej: superusuario 'admin').

    Hereda de ModelBackend, por lo que:
    - Las contraseñas se verifican con el hash seguro de Django.
    - Los usuarios inactivos (is_active=False) no pueden ingresar.
    - Los permisos se obtienen de los grupos (roles) del usuario.
    """

    def authenticate(self, request, username=None, password=None, **kwargs):
        if username is None or password is None:
            return None

        usuario = self.buscar_usuario(username.strip())

        if usuario is None:
            # Se calcula un hash igualmente para no revelar, por el tiempo
            # de respuesta, si el usuario existe o no.
            get_user_model()().set_password(password)
            return None

        if usuario.check_password(password) and self.user_can_authenticate(usuario):
            return usuario

        return None

    def buscar_usuario(self, identificador):
        User = get_user_model()

        if "@" in identificador:
            coincidencias = User.objects.filter(email__iexact=identificador)
        else:
            coincidencias = User.objects.filter(
                perfil__rut=normalizar_rut(identificador)
            )

            if not coincidencias.exists():
                coincidencias = User.objects.filter(username=identificador)

        # Si hay más de una coincidencia el identificador es ambiguo
        # y no se permite el ingreso.
        if coincidencias.count() != 1:
            return None

        return coincidencias.first()
