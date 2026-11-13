from django.db import models
from rest_framework import serializers

from delegacionesAPP.forms import DelegacionForm, ServicioForm
from delegacionesAPP.models import Delegacion, Servicio
from sgr_maestrosAPP.forms import (
    CatalogoActividadForm,
    MetaForm,
    PeriodoForm,
)
from sgr_maestrosAPP.models import CatalogoActividad, Periodo
from sgr_maestrosAPP.models import Meta as MetaModelo
from tubo_gestionAPP.forms import CompromisoForm
from tubo_gestionAPP.models import Compromiso


# ============================================================
# VALIDACIÓN COMPARTIDA CON LA APLICACIÓN WEB
# ============================================================
# Un serializador convierte los modelos a JSON y valida el JSON recibido.
# Para que la API no tenga reglas distintas a la web, cada serializador
# valida además con el MISMO formulario del mantenedor web (ModelForm),
# que a su vez ejecuta las validaciones del modelo (clean). Así, por
# ejemplo, la suma de ponderaciones de las metas o el código único del
# catálogo se controlan en un solo lugar.

class ValidacionWebMixin:
    """Valida los datos de entrada con el formulario web del mantenedor."""

    formulario = None

    def argumentos_formulario(self, attrs):
        """Argumentos extra que necesita el formulario (ej. delegación)."""
        return {}

    def datos_formulario(self, attrs):
        """
        Arma los datos del formulario: lo que llegó en la solicitud y, para
        los campos que no llegaron (PATCH o campos de solo lectura), el
        valor actual del registro o el valor por defecto del modelo.
        """
        modelo = self.Meta.model
        datos = {}

        for campo in self.formulario._meta.fields:
            if campo in attrs:
                valor = attrs[campo]
            elif self.instance is not None:
                valor = getattr(self.instance, campo)
            else:
                campo_modelo = modelo._meta.get_field(campo)
                if not campo_modelo.has_default():
                    continue
                valor = campo_modelo.get_default()

            if isinstance(valor, models.Model):
                valor = valor.pk

            if valor is not None:
                datos[campo] = valor

        return datos

    def validate(self, attrs):
        attrs = super().validate(attrs)

        formulario = self.formulario(
            data=self.datos_formulario(attrs),
            instance=self.instance,
            **self.argumentos_formulario(attrs),
        )

        if not formulario.is_valid():
            errores = {}
            for campo, mensajes in formulario.errors.items():
                clave = "non_field_errors" if campo == "__all__" else campo
                errores[clave] = list(mensajes)
            raise serializers.ValidationError(errores)

        # Se guardan los valores normalizados por el formulario
        # (ej. código en mayúsculas, textos sin espacios sobrantes).
        for campo in attrs:
            if campo in formulario.cleaned_data:
                attrs[campo] = formulario.cleaned_data[campo]

        return attrs


# ============================================================
# DELEGACIONES Y SERVICIOS
# ============================================================

class DelegacionSerializer(ValidacionWebMixin, serializers.ModelSerializer):
    formulario = DelegacionForm

    class Meta:
        model = Delegacion
        fields = [
            "id",
            "nombre",
            "direccion",
            "encargado",
            "email",
            "telefono",
            "celular",
            "activo",
        ]
        read_only_fields = ["activo"]
        extra_kwargs = {
            "nombre": {"help_text": "Nombre de la delegación territorial."},
            "direccion": {"help_text": "Dirección de la delegación."},
            "encargado": {"help_text": "Nombre del responsable."},
            "email": {"help_text": "Correo de contacto."},
            "activo": {"help_text": "False si la delegación fue dada de baja."},
        }


class ServicioSerializer(ValidacionWebMixin, serializers.ModelSerializer):
    formulario = ServicioForm

    delegacion_nombre = serializers.CharField(
        source="delegacion.nombre",
        read_only=True,
    )

    class Meta:
        model = Servicio
        fields = [
            "id",
            "delegacion",
            "delegacion_nombre",
            "nombre",
            "activo",
        ]
        read_only_fields = ["activo"]
        extra_kwargs = {
            "delegacion": {
                "help_text": (
                    "Id de la delegación a la que pertenece. No se puede "
                    "cambiar después de crear el servicio."
                ),
            },
            "nombre": {"help_text": "Nombre del servicio municipal."},
        }

    def delegacion_destino(self, attrs):
        if "delegacion" in attrs:
            return attrs["delegacion"]
        return self.instance.delegacion if self.instance else None

    def argumentos_formulario(self, attrs):
        return {"delegacion": self.delegacion_destino(attrs)}

    def validate(self, attrs):
        delegacion = self.delegacion_destino(attrs)

        if self.instance is not None and delegacion != self.instance.delegacion:
            raise serializers.ValidationError({
                "delegacion": (
                    "No se puede cambiar la delegación de un servicio."
                )
            })

        if self.instance is None and delegacion and not delegacion.activo:
            raise serializers.ValidationError({
                "delegacion": (
                    "No se pueden agregar servicios a una delegación "
                    "dada de baja."
                )
            })

        return super().validate(attrs)


# ============================================================
# COMPROMISOS (TUBO DE GESTIÓN)
# ============================================================

class CompromisoSerializer(ValidacionWebMixin, serializers.ModelSerializer):
    """
    Solo la tarea es editable. El cumplimiento cambia únicamente con el
    registro de avance (T2) y la delegación/servicio con la asignación
    (T1), igual que en la web; el estado del semáforo es calculado.
    """

    formulario = CompromisoForm

    delegacion_nombre = serializers.CharField(
        source="delegacion.nombre",
        read_only=True,
        default=None,
    )
    servicio_nombre = serializers.CharField(
        source="servicio.nombre",
        read_only=True,
        default=None,
    )

    class Meta:
        model = Compromiso
        fields = [
            "id",
            "tarea",
            "cumplimiento",
            "estado",
            "delegacion",
            "delegacion_nombre",
            "servicio",
            "servicio_nombre",
            "activo",
        ]
        read_only_fields = [
            "cumplimiento",
            "estado",
            "delegacion",
            "servicio",
            "activo",
        ]
        extra_kwargs = {
            "tarea": {"help_text": "Tarea o compromiso a cumplir."},
            "cumplimiento": {"help_text": "Porcentaje de avance (0 a 100)."},
            "estado": {
                "help_text": (
                    "Semáforo calculado: verde (90% o más), amarillo "
                    "(60% a 89%) o rojo (menos de 60%)."
                ),
            },
        }


# ============================================================
# TABLAS MAESTRAS: CATÁLOGO, PERÍODOS Y METAS
# ============================================================

class CatalogoActividadSerializer(
    ValidacionWebMixin,
    serializers.ModelSerializer,
):
    formulario = CatalogoActividadForm

    puntua = serializers.BooleanField(
        read_only=True,
        help_text="True si la actividad suma puntaje (R5).",
    )

    class Meta:
        model = CatalogoActividad
        fields = [
            "id",
            "codigo",
            "nombre",
            "descripcion",
            "area",
            "tipo_gestion",
            "puntua",
            "activo",
        ]
        read_only_fields = ["activo"]
        extra_kwargs = {
            "codigo": {"help_text": "Código único (se guarda en mayúsculas)."},
            "nombre": {"help_text": "Nombre de la actividad."},
            "area": {"help_text": "Área municipal (opcional)."},
        }


class ResumenCargoSerializer(serializers.Serializer):
    cargo = serializers.CharField(help_text="Cargo o 'Sin cargo'.")
    suma = serializers.DecimalField(max_digits=6, decimal_places=2)
    completo = serializers.BooleanField(help_text="True si suma 100%.")
    general = serializers.BooleanField(help_text="True para metas sin cargo.")


class PeriodoSerializer(ValidacionWebMixin, serializers.ModelSerializer):
    formulario = PeriodoForm

    ponderaciones_por_cargo = ResumenCargoSerializer(
        source="resumen_ponderaciones_por_cargo",
        many=True,
        read_only=True,
    )

    class Meta:
        model = Periodo
        fields = [
            "id",
            "codigo",
            "nombre",
            "fecha_inicio",
            "fecha_fin",
            "cerrado",
            "ponderaciones_por_cargo",
        ]
        extra_kwargs = {
            "codigo": {"help_text": "Código único del período."},
            "cerrado": {
                "help_text": (
                    "Para cerrar, las metas activas de cada cargo deben "
                    "sumar exactamente 100%. Un período cerrado no se "
                    "puede modificar."
                ),
            },
        }


class MetaSerializer(ValidacionWebMixin, serializers.ModelSerializer):
    formulario = MetaForm

    periodo_codigo = serializers.CharField(
        source="periodo.codigo",
        read_only=True,
    )
    actividad_nombre = serializers.CharField(
        source="actividad.nombre",
        read_only=True,
    )
    cargo_nombre = serializers.CharField(
        source="cargo.nombre",
        read_only=True,
        default=None,
    )

    class Meta:
        model = MetaModelo
        fields = [
            "id",
            "codigo",
            "nombre",
            "descripcion",
            "periodo",
            "periodo_codigo",
            "actividad",
            "actividad_nombre",
            "cargo",
            "cargo_nombre",
            "valor_objetivo",
            "ponderacion",
            "activo",
        ]
        read_only_fields = ["activo"]
        extra_kwargs = {
            "periodo": {"help_text": "Id de un período abierto."},
            "actividad": {"help_text": "Id de una actividad activa."},
            "cargo": {
                "help_text": (
                    "Id del cargo (null = meta general). Las metas activas "
                    "de un período y cargo no pueden superar el 100%."
                ),
            },
            "ponderacion": {"help_text": "Peso porcentual (0 a 100)."},
        }
