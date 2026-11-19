from rest_framework import serializers

from apiAPP.serializers import ValidacionWebMixin
from seguridadAPP.perfiles import ADMINISTRADOR, perfil_de

from .forms import ContactoEmergenciaForm, ZonaRiesgoForm
from .models import ContactoEmergencia, ZonaRiesgo


# ============================================================
# PROTECCIÓN DE DATOS SENSIBLES POR PERFIL
# ============================================================
# Perfil Administrador -> ve todos los campos.
# Perfil Usuario (Supervisor y Administrativo) -> no ve los campos
# definidos como sensibles (teléfonos, correos, coordenadas exactas y
# datos personales de vecinos o funcionarios). Los campos no se envían
# vacíos: se quitan de la respuesta JSON.

class CamposSensiblesMixin:
    """Quita de la respuesta los `campos_sensibles` si no es Administrador."""

    campos_sensibles = ()

    def ve_datos_sensibles(self):
        request = self.context.get("request")
        usuario = getattr(request, "user", None)
        return perfil_de(usuario) == ADMINISTRADOR

    def to_representation(self, instancia):
        datos = super().to_representation(instancia)

        if not self.ve_datos_sensibles():
            for campo in self.campos_sensibles:
                datos.pop(campo, None)

        return datos


class FormularioConUsuarioMixin:
    """Entrega el usuario al formulario web para aplicar el ámbito."""

    def argumentos_formulario(self, attrs):
        request = self.context.get("request")
        return {"usuario": getattr(request, "user", None)}


SOLO_ADMINISTRADOR = " Dato sensible: solo lo recibe el perfil Administrador."


# ============================================================
# MANTENEDOR 1: ZONAS DE RIESGO
# ============================================================

class ZonaRiesgoSerializer(
    CamposSensiblesMixin,
    FormularioConUsuarioMixin,
    ValidacionWebMixin,
    serializers.ModelSerializer,
):
    formulario = ZonaRiesgoForm
    campos_sensibles = ("coordenadas_aprox",)

    delegacion_nombre = serializers.CharField(
        source="delegacion.nombre", read_only=True
    )

    class Meta:
        model = ZonaRiesgo
        fields = [
            "id",
            "nombre",
            "delegacion",
            "delegacion_nombre",
            "nivel_peligro",
            "descripcion_riesgo",
            "coordenadas_aprox",
            "activo",
        ]
        read_only_fields = ["activo"]
        extra_kwargs = {
            "nombre": {"help_text": "Nombre de la zona (único por delegación)."},
            "delegacion": {"help_text": "Id de la delegación (debe ser la suya si no es Administrador)."},
            "nivel_peligro": {"help_text": "bajo, medio, alto o critico."},
            "coordenadas_aprox": {"help_text": "Latitud, longitud." + SOLO_ADMINISTRADOR},
            "activo": {"help_text": "False si la zona fue dada de baja."},
        }


# ============================================================
# MANTENEDOR 2: CONTACTOS DE EMERGENCIA
# ============================================================

class ContactoEmergenciaSerializer(
    CamposSensiblesMixin,
    FormularioConUsuarioMixin,
    ValidacionWebMixin,
    serializers.ModelSerializer,
):
    formulario = ContactoEmergenciaForm
    campos_sensibles = ("telefono", "email")

    delegacion_nombre = serializers.CharField(
        source="delegacion.nombre", read_only=True
    )
    zona_nombre = serializers.CharField(
        source="zona_asignada.nombre", read_only=True, default=None
    )

    class Meta:
        model = ContactoEmergencia
        fields = [
            "id",
            "nombre",
            "cargo",
            "telefono",
            "email",
            "delegacion",
            "delegacion_nombre",
            "zona_asignada",
            "zona_nombre",
            "activo",
        ]
        read_only_fields = ["activo"]
        extra_kwargs = {
            "telefono": {"help_text": "Teléfono del contacto." + SOLO_ADMINISTRADOR},
            "email": {"help_text": "Correo del contacto." + SOLO_ADMINISTRADOR},
            "zona_asignada": {"help_text": "Id de una zona de la misma delegación (opcional)."},
            "activo": {"help_text": "False si el contacto fue dado de baja."},
        }
