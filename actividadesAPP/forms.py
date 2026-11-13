"""Formulario de registro diario de actividades del SGR (EVA 3)."""

from django import forms
from django.db.models import Q
from django.utils import timezone

from sgr_maestrosAPP.models import CatalogoActividad

from .models import RegistroActividad


class RegistroActividadForm(forms.ModelForm):
    """Recibe datos del vecino; los campos de control los define el servidor."""

    class Meta:
        model = RegistroActividad
        fields = [
            "actividad",
            "fecha_actividad",
            "solicitante_tipo",
            "nombre_usuario",
            "telefono_usuario",
            "detalle",
        ]
        labels = {
            "actividad": "Actividad realizada",
            "fecha_actividad": "Fecha de la actividad",
            "solicitante_tipo": "Tipo de solicitante",
            "nombre_usuario": "Nombre del vecino o usuario",
            "telefono_usuario": "Teléfono del vecino o usuario",
            "detalle": "Detalle de la gestión",
        }
        help_texts = {
            "nombre_usuario": "Si falta el nombre, el registro se guarda sin puntaje.",
            "telefono_usuario": (
                "Teléfono chileno de 9 dígitos (también acepta +56). "
                "Si falta o no es válido, el registro se guarda sin puntaje."
            ),
            "detalle": "Máximo 1.000 caracteres.",
        }
        widgets = {
            "actividad": forms.Select(attrs={"class": "form-select"}),
            "fecha_actividad": forms.DateInput(
                format="%Y-%m-%d",
                attrs={"class": "form-control", "type": "date"},
            ),
            "solicitante_tipo": forms.Select(attrs={"class": "form-select"}),
            "nombre_usuario": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Nombre y apellido",
                "autocomplete": "name",
            }),
            "telefono_usuario": forms.TextInput(attrs={
                "class": "form-control",
                "type": "tel",
                "placeholder": "912345678",
                "autocomplete": "tel",
            }),
            "detalle": forms.Textarea(attrs={
                "class": "form-control",
                "rows": 3,
                "maxlength": 1000,
                "placeholder": "Describe brevemente la actividad realizada",
            }),
        }

    def __init__(self, *args, funcionario=None, **kwargs):
        """La vista debe pasar el PerfilUsuario autenticado, no datos del POST."""
        self.funcionario = funcionario
        super().__init__(*args, **kwargs)

        # Solo se pueden seleccionar actividades activas del catálogo.
        # Si se edita un registro histórico, se conserva su actividad.
        filtro = Q(activo=True)
        if self.instance.pk and self.instance.actividad_id:
            filtro |= Q(pk=self.instance.actividad_id)
        self.fields["actividad"].queryset = CatalogoActividad.objects.filter(
            filtro
        ).distinct().order_by("nombre")

        if not self.is_bound and not self.instance.pk:
            self.initial.setdefault("fecha_actividad", timezone.localdate())

    def clean_nombre_usuario(self):
        return " ".join((self.cleaned_data.get("nombre_usuario") or "").split())

    def clean_telefono_usuario(self):
        # No rechazar contactos incompletos: R2 exige guardar sin puntaje.
        return (self.cleaned_data.get("telefono_usuario") or "").strip()

    def save(self, commit=True):
        if self.funcionario is None or self.funcionario.pk is None:
            raise ValueError(
                "La vista debe indicar el PerfilUsuario del funcionario autenticado."
            )

        registro = super().save(commit=False)
        registro.funcionario = self.funcionario
        if commit:
            # El modelo aplica R1-R5, el cierre semanal y el límite de 7.
            registro.save()
        return registro
