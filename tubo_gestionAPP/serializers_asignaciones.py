from rest_framework import serializers

from apiAPP.serializers import SOLO_ADMINISTRADOR, CamposSensiblesMixin

from .models import AsignacionCompromiso


# ============================================================
# API DE LA TRANSACCIÓN 1 (T1): ASIGNACIÓN DEL COMPROMISO
# ============================================================

def _nombre(usuario):
    if usuario is None:
        return None
    return usuario.get_full_name() or usuario.username


class AsignacionSerializer(CamposSensiblesMixin, serializers.ModelSerializer):
    """Salida: una asignación del historial del compromiso."""

    # Nombres de los funcionarios: datos personales, solo Administrador.
    campos_sensibles = ("asignado_por", "anulado_por_nombre")

    compromiso_tarea = serializers.CharField(source="compromiso.tarea", read_only=True)
    delegacion_nombre = serializers.CharField(source="delegacion.nombre", read_only=True)
    servicio_nombre = serializers.CharField(source="servicio.nombre", read_only=True)
    asignado_por = serializers.SerializerMethodField(
        help_text="Funcionario que asignó." + SOLO_ADMINISTRADOR
    )
    anulado_por_nombre = serializers.SerializerMethodField(
        help_text="Funcionario que anuló." + SOLO_ADMINISTRADOR
    )
    vigente = serializers.BooleanField(source="activo", read_only=True)

    class Meta:
        model = AsignacionCompromiso
        fields = [
            "id",
            "compromiso",
            "compromiso_tarea",
            "delegacion",
            "delegacion_nombre",
            "servicio",
            "servicio_nombre",
            "observacion",
            "asignado_por",
            "fecha_asignacion",
            "vigente",
            "anulada",
            "motivo_anulacion",
            "anulado_por_nombre",
            "fecha_anulacion",
        ]
        read_only_fields = fields

    def get_asignado_por(self, asignacion) -> str:
        return _nombre(asignacion.usuario_asignador)

    def get_anulado_por_nombre(self, asignacion) -> str | None:
        return _nombre(asignacion.anulado_por)


class AsignacionCrearSerializer(serializers.Serializer):
    """Entrada de POST: qué compromiso se asigna y a dónde."""

    compromiso = serializers.IntegerField(help_text="Id del compromiso.")
    delegacion = serializers.IntegerField(
        help_text="Id de la delegación (la suya si no es Administrador)."
    )
    servicio = serializers.IntegerField(
        help_text="Id de un servicio activo de esa delegación."
    )
    observacion = serializers.CharField(
        max_length=1000, required=False, allow_blank=True, default=""
    )


class AsignacionCorregirSerializer(serializers.Serializer):
    """Entrada de PUT/PATCH: la delegación y el servicio se cambian reasignando."""

    observacion = serializers.CharField(max_length=1000, allow_blank=True)


class AsignacionAnularSerializer(serializers.Serializer):
    motivo = serializers.CharField(
        max_length=1000, help_text="Por qué se anula la asignación (obligatorio)."
    )
