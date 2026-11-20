from rest_framework import serializers

from apiAPP.serializers import ValidacionWebMixin
from emergenciasTerritorialesAPP.models import ContactoEmergencia, ZonaRiesgo
from emergenciasTerritorialesAPP.serializers import (
    SOLO_ADMINISTRADOR,
    CamposSensiblesMixin,
    FormularioConUsuarioMixin,
)

from .forms import ReporteCiudadanoForm
from .models import DerivacionReporte, ReporteCiudadano


# ============================================================
# REPORTES CIUDADANOS
# ============================================================
# Estado, zona, contacto y fechas son de solo lectura: cambian
# únicamente por la transacción de derivación.

class ReporteCiudadanoSerializer(
    CamposSensiblesMixin,
    FormularioConUsuarioMixin,
    ValidacionWebMixin,
    serializers.ModelSerializer,
):
    formulario = ReporteCiudadanoForm
    campos_sensibles = ("nombre_vecino", "telefono_vecino", "email_vecino")

    delegacion_nombre = serializers.CharField(source="delegacion.nombre", read_only=True)
    zona_nombre = serializers.CharField(source="zona.nombre", read_only=True, default=None)
    contacto_nombre = serializers.CharField(
        source="contacto.nombre", read_only=True, default=None
    )

    class Meta:
        model = ReporteCiudadano
        fields = [
            "id",
            "delegacion",
            "delegacion_nombre",
            "tipo",
            "prioridad",
            "descripcion",
            "ubicacion",
            "nombre_vecino",
            "telefono_vecino",
            "email_vecino",
            "estado",
            "zona",
            "zona_nombre",
            "contacto",
            "contacto_nombre",
            "fecha_reporte",
            "fecha_resolucion",
            "activo",
        ]
        read_only_fields = [
            "estado",
            "zona",
            "contacto",
            "fecha_reporte",
            "fecha_resolucion",
            "activo",
        ]
        extra_kwargs = {
            "tipo": {"help_text": "alumbrado, baches, basura, seguridad, verde u otros."},
            "prioridad": {"help_text": "alta, media o baja."},
            "nombre_vecino": {"help_text": "Vecino que informa." + SOLO_ADMINISTRADOR},
            "telefono_vecino": {"help_text": "Teléfono del vecino." + SOLO_ADMINISTRADOR},
            "email_vecino": {"help_text": "Correo del vecino." + SOLO_ADMINISTRADOR},
            "estado": {"help_text": "pendiente, derivado o resuelto. Solo cambia por la transacción."},
        }


# ============================================================
# TRANSACCIÓN: DERIVACIÓN DEL REPORTE
# ============================================================

class DerivacionSerializer(CamposSensiblesMixin, serializers.ModelSerializer):
    """Salida: una derivación del historial."""

    campos_sensibles = ("usuario_nombre",)

    zona_nombre = serializers.CharField(source="zona.nombre", read_only=True)
    contacto_nombre = serializers.CharField(source="contacto.nombre", read_only=True)
    reporte_estado = serializers.CharField(source="reporte.estado", read_only=True)
    usuario_nombre = serializers.SerializerMethodField(
        help_text="Funcionario que registró la derivación." + SOLO_ADMINISTRADOR
    )

    class Meta:
        model = DerivacionReporte
        fields = [
            "id",
            "reporte",
            "reporte_estado",
            "zona",
            "zona_nombre",
            "contacto",
            "contacto_nombre",
            "observacion",
            "usuario_nombre",
            "fecha",
            "activo",
            "anulada",
        ]
        read_only_fields = fields

    def get_usuario_nombre(self, derivacion) -> str:
        usuario = derivacion.usuario
        return usuario.get_full_name() or usuario.username


class DerivacionCrearSerializer(serializers.Serializer):
    """Entrada de POST: qué reporte se deriva y a dónde."""

    reporte = serializers.PrimaryKeyRelatedField(queryset=ReporteCiudadano.objects.all())
    zona = serializers.PrimaryKeyRelatedField(queryset=ZonaRiesgo.objects.all())
    contacto = serializers.PrimaryKeyRelatedField(
        queryset=ContactoEmergencia.objects.all()
    )
    observacion = serializers.CharField(
        max_length=1000, required=False, allow_blank=True, default=""
    )


class DerivacionModificarSerializer(serializers.Serializer):
    """Entrada de PUT/PATCH: corrige la derivación vigente."""

    zona = serializers.PrimaryKeyRelatedField(queryset=ZonaRiesgo.objects.all())
    contacto = serializers.PrimaryKeyRelatedField(
        queryset=ContactoEmergencia.objects.all()
    )
    observacion = serializers.CharField(max_length=1000, allow_blank=True)
