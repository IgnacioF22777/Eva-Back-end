from datetime import date

from django import forms

from delegacionesAPP.models import Delegacion
from tubo_gestionAPP.ambito import delegacion_id_de, es_global

from .models import OrganizacionComunitaria


class OrganizacionForm(forms.ModelForm):

    class Meta:
        model = OrganizacionComunitaria

        fields = [
            "nombre",
            "tipo",
            "numero_registro",
            "delegacion",
            "domicilio",
            "socios_activos",
            "fecha_constitucion",
            "fecha_inscripcion",
            "registro_directiva",
            "verificada",
            "observaciones",
        ]

        widgets = {
            "nombre": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Ej: Junta de Vecinos Villa El Indio",
                "autofocus": True,
            }),
            "tipo": forms.Select(attrs={"class": "form-select"}),
            "numero_registro": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Ej: 4006",
            }),
            "delegacion": forms.Select(attrs={"class": "form-select"}),
            "domicilio": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Calle, número, sector",
            }),
            "socios_activos": forms.NumberInput(attrs={"class": "form-control", "min": 0}),
            "fecha_constitucion": forms.DateInput(
                format="%Y-%m-%d", attrs={"class": "form-control", "type": "date"}
            ),
            "fecha_inscripcion": forms.DateInput(
                format="%Y-%m-%d", attrs={"class": "form-control", "type": "date"}
            ),
            "registro_directiva": forms.TextInput(attrs={"class": "form-control"}),
            "verificada": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "observaciones": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
        }

    def __init__(self, *args, usuario=None, **kwargs):
        super().__init__(*args, **kwargs)

        delegaciones = Delegacion.objects.filter(activo=True).order_by("nombre")
        self.fields["delegacion"].empty_label = "Sin delegación asignada"

        # Ámbito territorial: sin visión global solo se ofrece la propia.
        if usuario is not None and not es_global(usuario):
            delegaciones = delegaciones.filter(pk=delegacion_id_de(usuario))
            self.fields["delegacion"].required = True
            self.fields["delegacion"].empty_label = None

        self.fields["delegacion"].queryset = delegaciones

    def clean(self):
        datos = super().clean()
        constitucion = datos.get("fecha_constitucion")
        inscripcion = datos.get("fecha_inscripcion")
        hoy = date.today()

        for campo in ("fecha_constitucion", "fecha_inscripcion"):
            fecha = datos.get(campo)
            if fecha and fecha > hoy:
                self.add_error(campo, "La fecha no puede ser futura.")

        if constitucion and inscripcion and inscripcion < constitucion:
            self.add_error(
                "fecha_inscripcion",
                "La inscripción no puede ser anterior a la constitución.",
            )

        return datos
