from rest_framework import serializers

from apiAPP.serializers import (  # noqa: F401 (se reexportan)
    SOLO_ADMINISTRADOR,
    CamposSensiblesMixin,
    ValidacionWebMixin,
)

from .forms import ContactoEmergenciaForm, ZonaRiesgoForm
from .models import ContactoEmergencia, ZonaRiesgo


# Los datos sensibles se ocultan con CamposSensiblesMixin (apiAPP): el
# perfil Administrador los recibe y el perfil Usuario (Supervisor y
# Administrativo) no.

class FormularioConUsuarioMixin:
    """Entrega el usuario al formulario web para aplicar el ámbito."""

    def argumentos_formulario(self, attrs):
        request = self.context.get("request")
        return {"usuario": getattr(request, "user", None)}


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
