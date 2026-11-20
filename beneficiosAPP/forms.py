from django import forms

from .models import CampanaRegalo, NinoInscrito


class NinoInscritoForm(forms.ModelForm):
    class Meta:
        model = NinoInscrito
        fields = ["campana", "rut", "nombre", "apellido", "sexo", "fecha_nacimiento"]
        widgets = {
            "campana": forms.Select(attrs={"class": "form-select"}),
            "rut": forms.TextInput(attrs={"class": "form-control", "placeholder": "12.345.678-9"}),
            "nombre": forms.TextInput(attrs={"class": "form-control"}),
            "apellido": forms.TextInput(attrs={"class": "form-control"}),
            "sexo": forms.Select(attrs={"class": "form-select"}),
            "fecha_nacimiento": forms.DateInput(
                attrs={"class": "form-control", "type": "date"}, format="%Y-%m-%d"
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Al inscribir, solo campañas con inscripciones abiertas. Al
        # corregir, la campaña no se cambia (se anula y se inscribe de nuevo).
        if self.instance.pk:
            self.fields["campana"].queryset = CampanaRegalo.objects.filter(
                pk=self.instance.campana_id
            )
            self.fields["campana"].disabled = True
        else:
            abiertas = [c.pk for c in CampanaRegalo.objects.filter(activo=True) if c.inscripciones_abiertas()]
            self.fields["campana"].queryset = CampanaRegalo.objects.filter(pk__in=abiertas)

        self.fields["campana"].empty_label = "Seleccione una campaña"
        self.fields["sexo"].choices = [("", "Seleccione")] + NinoInscrito.SEXOS


class CampanaRegaloForm(forms.ModelForm):
    class Meta:
        model = CampanaRegalo
        fields = ["tipo", "anio", "fecha_inicio", "fecha_fin", "edad_maxima"]
        widgets = {
            "tipo": forms.Select(attrs={"class": "form-select"}),
            "anio": forms.NumberInput(attrs={"class": "form-control"}),
            "fecha_inicio": forms.DateInput(
                attrs={"class": "form-control", "type": "date"}, format="%Y-%m-%d"
            ),
            "fecha_fin": forms.DateInput(
                attrs={"class": "form-control", "type": "date"}, format="%Y-%m-%d"
            ),
            "edad_maxima": forms.NumberInput(attrs={"class": "form-control", "min": 0, "max": 17}),
        }
