from django import forms

from delegacionesAPP.models import Delegacion
from tubo_gestionAPP.ambito import delegacion_id_de, es_global

from .models import CartaOficinaPartes


class CartaForm(forms.ModelForm):

    class Meta:
        model = CartaOficinaPartes

        fields = [
            "delegacion",
            "fecha_recepcion",
            "numero_ingreso",
            "destinatario",
            "remitente",
            "telefono_contacto",
            "tema",
            "fecha_actividad",
            "encargado_seguimiento",
            "estado",
            "pronunciamiento",
            "derivada_a",
            "observacion",
        ]

        widgets = {
            "delegacion": forms.Select(attrs={"class": "form-select"}),
            "fecha_recepcion": forms.DateInput(
                format="%Y-%m-%d", attrs={"class": "form-control", "type": "date"}
            ),
            "numero_ingreso": forms.TextInput(attrs={"class": "form-control", "placeholder": "Ej: 10093"}),
            "destinatario": forms.Select(attrs={"class": "form-select"}),
            "remitente": forms.TextInput(attrs={
                "class": "form-control", "placeholder": "Nombre de la persona u organización",
            }),
            "telefono_contacto": forms.TextInput(attrs={
                "class": "form-control", "placeholder": "+56 9 1234 5678",
            }),
            "tema": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "fecha_actividad": forms.TextInput(attrs={"class": "form-control"}),
            "encargado_seguimiento": forms.TextInput(attrs={"class": "form-control"}),
            "estado": forms.Select(attrs={"class": "form-select"}),
            "pronunciamiento": forms.Select(attrs={"class": "form-select"}),
            "derivada_a": forms.TextInput(attrs={"class": "form-control"}),
            "observacion": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
        }

    def __init__(self, *args, usuario=None, **kwargs):
        super().__init__(*args, **kwargs)

        delegaciones = Delegacion.objects.filter(activo=True).order_by("nombre")
        if usuario is not None and not es_global(usuario):
            delegaciones = delegaciones.filter(pk=delegacion_id_de(usuario))
        self.fields["delegacion"].queryset = delegaciones
        self.fields["delegacion"].empty_label = None if delegaciones.count() == 1 else "Seleccione una delegación"
