from django.urls import reverse
from rest_framework import serializers

from apiAPP.serializers import SOLO_ADMINISTRADOR, CamposSensiblesMixin

from .adjuntos import MAX_ARCHIVOS
from .models import AdjuntoAvance, RegistroAvance


# ============================================================
# API DE LA TRANSACCIÓN 2 (T2): REGISTRO DE AVANCE
# ============================================================

class AdjuntoAvanceSerializer(serializers.ModelSerializer):
    descarga = serializers.SerializerMethodField(
        help_text="Ruta de descarga protegida (exige sesión, permiso y ámbito)."
    )

    class Meta:
        model = AdjuntoAvance
        fields = ["id", "nombre_original", "tamano", "tipo_contenido", "descarga"]
        read_only_fields = fields

    def get_descarga(self, adjunto) -> str:
        return reverse("adjunto_descargar", args=[adjunto.pk])


class RegistroAvanceSerializer(CamposSensiblesMixin, serializers.ModelSerializer):
    """Salida: un avance del historial del compromiso."""

    # Nombres de los funcionarios: datos personales, solo Administrador.
    campos_sensibles = ("registrado_por", "anulado_por_nombre")

    compromiso_tarea = serializers.CharField(source="compromiso.tarea", read_only=True)
    cumplimiento_compromiso = serializers.IntegerField(
        source="compromiso.cumplimiento",
        read_only=True,
        help_text="Cumplimiento vigente del compromiso después de la operación.",
    )
    semaforo_compromiso = serializers.CharField(
        source="compromiso.estado", read_only=True
    )
    adjuntos = AdjuntoAvanceSerializer(many=True, read_only=True)
    registrado_por = serializers.SerializerMethodField(
        help_text="Funcionario que registró el avance." + SOLO_ADMINISTRADOR
    )
    anulado_por_nombre = serializers.SerializerMethodField(
        help_text="Funcionario que anuló el avance." + SOLO_ADMINISTRADOR
    )

    class Meta:
        model = RegistroAvance
        fields = [
            "id",
            "compromiso",
            "compromiso_tarea",
            "porcentaje_avance",
            "evidencia",
            "observacion",
            "adjuntos",
            "registrado_por",
            "fecha_registro",
            "anulado",
            "motivo_anulacion",
            "anulado_por_nombre",
            "fecha_anulacion",
            "cumplimiento_compromiso",
            "semaforo_compromiso",
        ]
        read_only_fields = fields

    @staticmethod
    def _nombre(usuario):
        if usuario is None:
            return None
        return usuario.get_full_name() or usuario.username

    def get_registrado_por(self, avance) -> str:
        return self._nombre(avance.usuario_registro)

    def get_anulado_por_nombre(self, avance) -> str | None:
        return self._nombre(avance.anulado_por)


class AvanceCrearSerializer(serializers.Serializer):
    """
    Entrada de POST (JSON o multipart/form-data si se adjuntan archivos).
    Los archivos se validan con las mismas reglas de la web: cantidad,
    tamaño y extensiones bloqueadas.
    """

    compromiso = serializers.IntegerField(help_text="Id del compromiso.")
    porcentaje_avance = serializers.IntegerField(
        min_value=0,
        max_value=100,
        help_text="Nuevo cumplimiento (0 a 100). No puede ser menor al vigente.",
    )
    evidencia = serializers.CharField(
        help_text="Referencia verificable: acta, correo, fotografía, documento o enlace."
    )
    observacion = serializers.CharField(required=False, allow_blank=True)
    adjuntos = serializers.ListField(
        child=serializers.FileField(),
        required=False,
        help_text=f"Archivos de respaldo (multipart/form-data), máximo {MAX_ARCHIVOS}.",
    )


class AvanceCorregirSerializer(serializers.Serializer):
    """Entrada de PUT/PATCH: el porcentaje no se corrige, se anula."""

    evidencia = serializers.CharField(max_length=2000)
    observacion = serializers.CharField(max_length=1000, allow_blank=True, required=False)


class AvanceAnularSerializer(serializers.Serializer):
    motivo = serializers.CharField(
        max_length=1000,
        help_text="Por qué se anula el avance (obligatorio).",
    )
