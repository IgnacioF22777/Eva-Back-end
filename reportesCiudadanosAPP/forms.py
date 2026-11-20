from django import forms

from emergenciasTerritorialesAPP.forms import FormularioConAmbitoMixin, validar_telefono
from emergenciasTerritorialesAPP.models import ContactoEmergencia, ZonaRiesgo

from .models import ReporteCiudadano


# ============================================================
# REGISTRO DEL REPORTE CIUDADANO
# ============================================================
# Estado, zona y contacto no se editan aquí: solo cambian por la
# transacción de derivación (reportesCiudadanosAPP/transaccion.py).

class ReporteCiudadanoForm(FormularioConAmbitoMixin, forms.ModelForm):
    class Meta:
        model = ReporteCiudadano
        fields = [
            "delegacion",
            "tipo",
            "prioridad",
            "descripcion",
            "ubicacion",
            "nombre_vecino",
            "telefono_vecino",
            "email_vecino",
        ]
        labels = {
            "delegacion": "Delegación",
            "tipo": "Tipo de reporte",
            "prioridad": "Prioridad",
            "descripcion": "Descripción",
            "ubicacion": "Ubicación",
            "nombre_vecino": "Nombre del vecino",
            "telefono_vecino": "Teléfono del vecino",
            "email_vecino": "Correo del vecino",
        }
        help_texts = {
            "telefono_vecino": "Opcional. Dato sensible: en la API solo lo ve el Administrador.",
            "email_vecino": "Opcional. Dato sensible: en la API solo lo ve el Administrador.",
        }
        widgets = {
            "delegacion": forms.Select(attrs={"class": "form-select"}),
            "tipo": forms.Select(attrs={"class": "form-select"}),
            "prioridad": forms.Select(attrs={"class": "form-select"}),
            "descripcion": forms.Textarea(attrs={
                "class": "form-control",
                "rows": 3,
                "maxlength": 500,
                "placeholder": "Qué ocurre",
            }),
            "ubicacion": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Calle, número o referencia",
            }),
            "nombre_vecino": forms.TextInput(attrs={"class": "form-control"}),
            "telefono_vecino": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "+56 9 0000 0000",
            }),
            "email_vecino": forms.EmailInput(attrs={"class": "form-control"}),
        }

    def __init__(self, *args, usuario=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.configurar_delegacion(usuario)

        # Un reporte ya derivado no cambia de delegación: su zona y su
        # contacto pertenecen a la delegación original.
        if self.instance.pk and self.instance.estado != "pendiente":
            self.fields["delegacion"].disabled = True

    def clean_descripcion(self):
        descripcion = (self.cleaned_data.get("descripcion") or "").strip()

        if not descripcion:
            raise forms.ValidationError("Describa el problema informado.")

        return descripcion

    def clean_ubicacion(self):
        ubicacion = (self.cleaned_data.get("ubicacion") or "").strip()

        if not ubicacion:
            raise forms.ValidationError("Indique la ubicación del problema.")

        return ubicacion

    def clean_telefono_vecino(self):
        telefono = (self.cleaned_data.get("telefono_vecino") or "").strip()
        return validar_telefono(telefono) if telefono else ""

    def clean_email_vecino(self):
        return (self.cleaned_data.get("email_vecino") or "").strip().lower()

    def clean(self):
        datos = super().clean()

        if self.instance.pk and self.instance.esta_resuelto:
            raise forms.ValidationError(
                "El reporte ya está resuelto: no se puede modificar."
            )

        return datos


# ============================================================
# TRANSACCIÓN: DERIVACIÓN
# ============================================================

class DerivacionForm(forms.Form):
    zona = forms.ModelChoiceField(
        queryset=ZonaRiesgo.objects.none(),
        label="Zona de riesgo",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    contacto = forms.ModelChoiceField(
        queryset=ContactoEmergencia.objects.none(),
        label="Contacto de emergencia",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    observacion = forms.CharField(
        label="Observación",
        required=False,
        max_length=1000,
        widget=forms.Textarea(attrs={
            "class": "form-control",
            "rows": 3,
            "maxlength": 1000,
            "placeholder": "Instrucciones para el contacto (opcional)",
        }),
    )

    def __init__(self, *args, reporte, **kwargs):
        super().__init__(*args, **kwargs)

        # Solo zonas y contactos activos de la delegación del reporte.
        self.fields["zona"].queryset = ZonaRiesgo.objects.filter(
            delegacion_id=reporte.delegacion_id,
            activo=True,
        )
        self.fields["contacto"].queryset = ContactoEmergencia.objects.filter(
            delegacion_id=reporte.delegacion_id,
            activo=True,
        )
