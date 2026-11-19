import re

from django import forms

from delegacionesAPP.models import Delegacion

from .ambito import delegaciones_permitidas
from .models import ContactoEmergencia, ZonaRiesgo


# Teléfonos: dígitos, espacios, guiones, paréntesis y "+" inicial.
# Se aceptan números cortos de emergencia como 131, 132 o 133.
PATRON_TELEFONO = re.compile(r"^\+?[\d\s\-()]{3,20}$")


def validar_telefono(valor):
    valor = (valor or "").strip()

    if not PATRON_TELEFONO.match(valor):
        raise forms.ValidationError(
            "Ingrese un teléfono válido: solo números, espacios, guiones "
            "o '+' (entre 3 y 20 caracteres)."
        )

    if len(re.sub(r"\D", "", valor)) < 3:
        raise forms.ValidationError("El teléfono debe tener al menos 3 dígitos.")

    return valor


class FormularioConAmbitoMixin:
    """
    Recibe el usuario para limitar las delegaciones a su ámbito. Sin
    usuario (por ejemplo, en pruebas de formulario) se ofrecen todas las
    delegaciones activas.
    """

    def configurar_delegacion(self, usuario):
        delegaciones = Delegacion.objects.filter(activo=True).order_by("nombre")

        if usuario is not None:
            delegaciones = delegaciones_permitidas(usuario, delegaciones)

        # Al editar se conserva la delegación actual aunque esté inactiva.
        if self.instance.pk and self.instance.delegacion_id:
            delegaciones = (
                delegaciones
                | Delegacion.objects.filter(pk=self.instance.delegacion_id)
            ).distinct()

        self.fields["delegacion"].queryset = delegaciones


# ============================================================
# MANTENEDOR 1: ZONAS DE RIESGO
# ============================================================

class ZonaRiesgoForm(FormularioConAmbitoMixin, forms.ModelForm):
    class Meta:
        model = ZonaRiesgo
        fields = [
            "nombre",
            "delegacion",
            "nivel_peligro",
            "descripcion_riesgo",
            "coordenadas_aprox",
        ]
        labels = {
            "nombre": "Nombre de la zona",
            "delegacion": "Delegación",
            "nivel_peligro": "Nivel de peligro",
            "descripcion_riesgo": "Descripción del riesgo",
            "coordenadas_aprox": "Coordenadas aproximadas",
        }
        help_texts = {
            "coordenadas_aprox": (
                "Opcional. Dato sensible: en la API solo lo ve el "
                "Administrador."
            ),
        }
        widgets = {
            "nombre": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Ej: Quebrada Peñuelas",
                "autofocus": True,
            }),
            "delegacion": forms.Select(attrs={"class": "form-select"}),
            "nivel_peligro": forms.Select(attrs={"class": "form-select"}),
            "descripcion_riesgo": forms.Textarea(attrs={
                "class": "form-control",
                "rows": 3,
                "maxlength": 500,
                "placeholder": "Qué riesgo existe y por qué",
            }),
            "coordenadas_aprox": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "-29.9027, -71.2519",
            }),
        }

    def __init__(self, *args, usuario=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.configurar_delegacion(usuario)

    def clean_nombre(self):
        nombre = (self.cleaned_data.get("nombre") or "").strip()

        if not nombre:
            raise forms.ValidationError("El nombre de la zona es obligatorio.")

        return nombre

    def clean_descripcion_riesgo(self):
        descripcion = (self.cleaned_data.get("descripcion_riesgo") or "").strip()

        if not descripcion:
            raise forms.ValidationError("Describa el riesgo de la zona.")

        return descripcion

    def clean(self):
        datos = super().clean()
        nombre = datos.get("nombre")
        delegacion = datos.get("delegacion")

        if nombre and delegacion:
            duplicada = ZonaRiesgo.objects.filter(
                nombre__iexact=nombre,
                delegacion=delegacion,
                activo=True,
            ).exclude(pk=self.instance.pk)

            if duplicada.exists():
                self.add_error(
                    "nombre",
                    "Ya existe una zona activa con este nombre en la "
                    "delegación.",
                )

        return datos


# ============================================================
# MANTENEDOR 2: CONTACTOS DE EMERGENCIA
# ============================================================

class ContactoEmergenciaForm(FormularioConAmbitoMixin, forms.ModelForm):
    class Meta:
        model = ContactoEmergencia
        fields = [
            "nombre",
            "cargo",
            "telefono",
            "email",
            "delegacion",
            "zona_asignada",
        ]
        labels = {
            "nombre": "Nombre",
            "cargo": "Cargo o unidad",
            "telefono": "Teléfono",
            "email": "Correo electrónico",
            "delegacion": "Delegación",
            "zona_asignada": "Zona asignada",
        }
        help_texts = {
            "telefono": "Dato sensible: en la API solo lo ve el Administrador.",
            "email": "Opcional. Dato sensible: en la API solo lo ve el Administrador.",
            "zona_asignada": "Opcional. Debe pertenecer a la misma delegación.",
        }
        widgets = {
            "nombre": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Ej: Central de Bomberos",
                "autofocus": True,
            }),
            "cargo": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Ej: Unidad de Emergencia",
            }),
            "telefono": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "+56 9 0000 0000",
            }),
            "email": forms.EmailInput(attrs={
                "class": "form-control",
                "placeholder": "contacto@laserena.cl",
            }),
            "delegacion": forms.Select(attrs={"class": "form-select"}),
            "zona_asignada": forms.Select(attrs={"class": "form-select"}),
        }

    def __init__(self, *args, usuario=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.configurar_delegacion(usuario)

        zonas = ZonaRiesgo.objects.filter(activo=True).select_related("delegacion")

        if self.instance.pk and self.instance.zona_asignada_id:
            zonas = (
                zonas | ZonaRiesgo.objects.filter(pk=self.instance.zona_asignada_id)
            ).distinct()

        self.fields["zona_asignada"].queryset = zonas.filter(
            delegacion__in=self.fields["delegacion"].queryset
        )
        self.fields["zona_asignada"].required = False

    def clean_nombre(self):
        nombre = (self.cleaned_data.get("nombre") or "").strip()

        if not nombre:
            raise forms.ValidationError("El nombre del contacto es obligatorio.")

        return nombre

    def clean_telefono(self):
        return validar_telefono(self.cleaned_data.get("telefono"))

    def clean_email(self):
        return (self.cleaned_data.get("email") or "").strip().lower()

    def clean(self):
        datos = super().clean()
        delegacion = datos.get("delegacion")
        zona = datos.get("zona_asignada")

        if delegacion and zona and zona.delegacion_id != delegacion.pk:
            self.add_error(
                "zona_asignada",
                "La zona asignada no pertenece a la delegación del contacto.",
            )

        return datos
