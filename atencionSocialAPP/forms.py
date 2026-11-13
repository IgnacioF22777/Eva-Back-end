from django import forms

from delegacionesAPP.models import Delegacion
from tubo_gestionAPP.ambito import delegacion_id_de, es_global

from .models import AtencionSocial


class AtencionSocialForm(forms.ModelForm):

    class Meta:
        model = AtencionSocial
        fields = [
            "delegacion", "fecha", "tipo", "subtipo",
            "nombre_vecino", "telefono_vecino", "derivada_a", "detalle",
        ]
        widgets = {
            "delegacion": forms.Select(attrs={"class": "form-select"}),
            "fecha": forms.DateInput(format="%Y-%m-%d", attrs={"class": "form-control", "type": "date"}),
            "tipo": forms.Select(attrs={"class": "form-select"}),
            "subtipo": forms.Select(attrs={"class": "form-select"}),
            "nombre_vecino": forms.TextInput(attrs={"class": "form-control"}),
            "telefono_vecino": forms.TextInput(attrs={"class": "form-control", "placeholder": "+56 9 1234 5678"}),
            "derivada_a": forms.TextInput(attrs={"class": "form-control"}),
            "detalle": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
        }

    def __init__(self, *args, usuario=None, **kwargs):
        super().__init__(*args, **kwargs)
        # Ámbito: sin visión global solo se registra en la delegación propia.
        delegaciones = Delegacion.objects.filter(activo=True).order_by("nombre")
        if usuario is not None and not es_global(usuario):
            delegaciones = delegaciones.filter(pk=delegacion_id_de(usuario))
        self.fields["delegacion"].queryset = delegaciones
        self.fields["delegacion"].empty_label = None if delegaciones.count() == 1 else "Seleccione una delegación"
        self.fields["subtipo"].choices = [("", "Sin subtipo")] + list(self.fields["subtipo"].choices)[1:]
