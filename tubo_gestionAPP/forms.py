from django import forms

from delegacionesAPP.models import Delegacion

from .models import Compromiso


class CompromisoForm(forms.ModelForm):
    class Meta:
        model = Compromiso

        fields = [
            "tarea",
            "cumplimiento",
            "delegacion",
        ]

        widgets = {
            "tarea": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Ej: Mejorar iluminación del sector",
                "autofocus": True,
            }),
            "cumplimiento": forms.NumberInput(attrs={
                "class": "form-control",
                "min": 0,
                "max": 100,
                "step": 1,
            }),
            "delegacion": forms.Select(attrs={
                "class": "form-select",
            }),
        }

        labels = {
            "tarea": "Tarea o compromiso",
            "cumplimiento": "Cumplimiento (%)",
            "delegacion": "Delegación responsable",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        campo = self.fields["delegacion"]
        campo.queryset = Delegacion.objects.all().order_by("nombre")
        campo.required = False
        campo.empty_label = "Sin delegación asignada"
        campo.label_from_instance = (
            lambda delegacion: (
                delegacion.nombre
                if delegacion.activo
                else f"{delegacion.nombre} (inactiva)"
            )
        )

    def clean_tarea(self):
        tarea = (self.cleaned_data.get("tarea") or "").strip()

        if not tarea:
            raise forms.ValidationError(
                "La tarea del compromiso es obligatoria."
            )

        return tarea

    def clean_cumplimiento(self):
        cumplimiento = self.cleaned_data.get("cumplimiento")

        if cumplimiento is None:
            raise forms.ValidationError(
                "Debe indicar el porcentaje de cumplimiento."
            )

        if not 0 <= cumplimiento <= 100:
            raise forms.ValidationError(
                "El cumplimiento debe estar entre 0 y 100."
            )

        return cumplimiento
