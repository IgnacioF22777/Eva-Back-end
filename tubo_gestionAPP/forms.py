from django import forms
from django.core.exceptions import ValidationError

from delegacionesAPP.models import Delegacion, Servicio

from .models import AsignacionCompromiso, Compromiso, RegistroAvance


class CompromisoForm(forms.ModelForm):
    """
    Formulario del mantenedor de compromisos.

    El cumplimiento y la delegación NO se editan aquí: el porcentaje solo
    cambia mediante el registro de avance y la asignación solo se realiza
    mediante la transacción de asignación. Así se evita el bypass de las
    operaciones atómicas.
    """

    class Meta:
        model = Compromiso

        fields = [
            "tarea",
        ]

        widgets = {
            "tarea": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Ej: Mejorar iluminación del sector",
                "autofocus": True,
            }),
        }

        labels = {
            "tarea": "Tarea o compromiso",
        }

    def clean_tarea(self):
        tarea = (self.cleaned_data.get("tarea") or "").strip()

        if not tarea:
            raise forms.ValidationError(
                "La tarea del compromiso es obligatoria."
            )

        return tarea


class AsignacionCompromisoForm(forms.ModelForm):
    """
    Formulario de la transacción T1: asignar un compromiso a una
    delegación y a un servicio de esa misma delegación.

    Solo muestra delegaciones y servicios activos, y el desplegable de
    servicios se filtra por la delegación seleccionada. La validación
    definitiva se repite en la vista, dentro de la transacción, porque el
    navegador no es una fuente confiable.
    """

    class Meta:
        model = AsignacionCompromiso

        fields = [
            "delegacion",
            "servicio",
            "observacion",
        ]

        widgets = {
            "delegacion": forms.Select(attrs={
                "class": "form-select",
            }),
            "servicio": forms.Select(attrs={
                "class": "form-select",
            }),
            "observacion": forms.Textarea(attrs={
                "class": "form-control",
                "rows": 3,
                "placeholder": (
                    "Instrucción para la unidad que ejecutará el compromiso."
                ),
            }),
        }

        labels = {
            "delegacion": "Delegación responsable",
            "servicio": "Servicio o unidad",
            "observacion": "Observación (opcional)",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["delegacion"].queryset = Delegacion.objects.filter(
            activo=True
        ).order_by("nombre")

        servicios = Servicio.objects.filter(
            activo=True,
            delegacion__activo=True,
        ).select_related("delegacion").order_by(
            "delegacion__nombre", "nombre"
        )

        delegacion_id = None

        if self.is_bound:
            delegacion_id = self.data.get("delegacion") or None
        elif self.instance.pk:
            delegacion_id = self.instance.delegacion_id

        if delegacion_id:
            try:
                delegacion_id = int(delegacion_id)
            except (TypeError, ValueError):
                delegacion_id = None

        if delegacion_id:
            servicios = servicios.filter(delegacion_id=delegacion_id)

        self.fields["servicio"].queryset = servicios

        self.fields["delegacion"].empty_label = "Seleccione una delegación"
        self.fields["servicio"].empty_label = "Seleccione un servicio"

    def clean(self):
        datos = super().clean()

        delegacion = datos.get("delegacion")
        servicio = datos.get("servicio")

        if delegacion and not delegacion.activo:
            raise ValidationError({
                "delegacion": "La delegación está dada de baja."
            })

        if servicio and not servicio.activo:
            raise ValidationError({
                "servicio": "El servicio está dado de baja."
            })

        if delegacion and servicio and servicio.delegacion_id != delegacion.pk:
            raise ValidationError({
                "servicio": (
                    "El servicio seleccionado no pertenece a la delegación."
                )
            })

        return datos


class RegistroAvanceForm(forms.ModelForm):
    """
    Formulario de la transacción T2: registrar el avance de un compromiso.

    El porcentaje no puede retroceder respecto del cumplimiento vigente.
    Esa comparación se hace en la vista, con el compromiso bloqueado,
    porque entre la validación del formulario y el guardado otro usuario
    podría haber registrado un avance mayor.
    """

    class Meta:
        model = RegistroAvance

        fields = [
            "porcentaje_avance",
            "evidencia",
            "observacion",
        ]

        widgets = {
            "porcentaje_avance": forms.NumberInput(attrs={
                "class": "form-control",
                "min": 0,
                "max": 100,
                "step": 1,
            }),
            "evidencia": forms.Textarea(attrs={
                "class": "form-control",
                "rows": 3,
                "placeholder": (
                    "Acta, correo, fotografía, documento o enlace que "
                    "respalda el avance informado."
                ),
            }),
            "observacion": forms.Textarea(attrs={
                "class": "form-control",
                "rows": 3,
                "placeholder": "Detalle adicional del avance (opcional).",
            }),
        }

        labels = {
            "porcentaje_avance": "Porcentaje de avance (%)",
            "evidencia": "Evidencia",
            "observacion": "Observación (opcional)",
        }

    def clean_evidencia(self):
        evidencia = (self.cleaned_data.get("evidencia") or "").strip()

        if not evidencia:
            raise forms.ValidationError(
                "La evidencia del avance es obligatoria."
            )

        return evidencia

    def clean_observacion(self):
        return (self.cleaned_data.get("observacion") or "").strip()
