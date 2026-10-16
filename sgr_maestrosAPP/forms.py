
from django import forms

from .models import (
    CatalogoActividad,
    Periodo,
    DetallePeriodo,
    Meta,
)


# ============================================================
# FORMULARIO 1: CATÁLOGO DE ACTIVIDADES
# ============================================================

class CatalogoActividadForm(forms.ModelForm):

    class Meta:
        model = CatalogoActividad

        fields = [
            "codigo",
            "nombre",
            "descripcion",
            "area",
            "activo",
        ]

        widgets = {
            "codigo": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Ej: ACT-ASEO-01",
            }),

            "nombre": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Nombre de la actividad",
            }),

            "descripcion": forms.Textarea(attrs={
                "class": "form-control",
                "rows": 3,
            }),

            "area": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Ej: Aseo y Ornato",
            }),

            "activo": forms.CheckboxInput(attrs={
                "class": "form-check-input",
            }),
        }

    def clean_codigo(self):
        codigo = self.cleaned_data["codigo"].strip().upper()

        if not codigo:
            raise forms.ValidationError(
                "El código es obligatorio."
            )

        return codigo


# ============================================================
# FORMULARIO 2: GESTIÓN DE PERÍODOS
# ============================================================

class PeriodoForm(forms.ModelForm):

    class Meta:
        model = Periodo

        fields = [
            "codigo",
            "nombre",
            "fecha_inicio",
            "fecha_fin",
            "cerrado",
        ]

        widgets = {
            "codigo": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Ej: PER-2026",
            }),

            "nombre": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Ej: Evaluación Anual 2026",
            }),

            "fecha_inicio": forms.DateInput(
                format="%Y-%m-%d",
                attrs={
                    "class": "form-control",
                    "type": "date",
                }
            ),

            "fecha_fin": forms.DateInput(
                format="%Y-%m-%d",
                attrs={
                    "class": "form-control",
                    "type": "date",
                }
            ),

            "cerrado": forms.CheckboxInput(attrs={
                "class": "form-check-input",
            }),
        }

    def clean_codigo(self):
        codigo = self.cleaned_data["codigo"].strip().upper()

        if Periodo.objects.exclude(
            pk=self.instance.pk
        ).filter(
            codigo__iexact=codigo
        ).exists():
            raise forms.ValidationError(
                "Ya existe un período con este código."
            )

        return codigo

    def clean(self):
        cleaned_data = super().clean()

        fecha_inicio = cleaned_data.get("fecha_inicio")
        fecha_fin = cleaned_data.get("fecha_fin")

        if fecha_inicio and fecha_fin:
            if fecha_fin < fecha_inicio:
                self.add_error(
                    "fecha_fin",
                    "La fecha de término no puede ser "
                    "anterior a la fecha de inicio."
                )

        return cleaned_data


# ============================================================
# FORMULARIO 3: DETALLE DE PERÍODO
# ============================================================

class DetallePeriodoForm(forms.ModelForm):

    class Meta:
        model = DetallePeriodo

        fields = [
            "periodo",
            "nombre",
            "fecha_inicio",
            "fecha_fin",
            "dias_computables",
            "observaciones",
        ]

        widgets = {
            "periodo": forms.Select(attrs={
                "class": "form-select",
            }),

            "nombre": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Ej: Primer semestre",
            }),

            "fecha_inicio": forms.DateInput(
                format="%Y-%m-%d",
                attrs={
                    "class": "form-control",
                    "type": "date",
                }
            ),

            "fecha_fin": forms.DateInput(
                format="%Y-%m-%d",
                attrs={
                    "class": "form-control",
                    "type": "date",
                }
            ),

            "dias_computables": forms.NumberInput(attrs={
                "class": "form-control",
                "min": "0",
                "placeholder": "Cantidad de días",
            }),

            "observaciones": forms.Textarea(attrs={
                "class": "form-control",
                "rows": 3,
                "placeholder": "Observaciones del detalle",
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["periodo"].queryset = (
            Periodo.objects.filter(cerrado=False)
        )

        self.fields["periodo"].empty_label = (
            "Seleccione un período"
        )

    def clean(self):
        cleaned_data = super().clean()

        periodo = cleaned_data.get("periodo")
        fecha_inicio = cleaned_data.get("fecha_inicio")
        fecha_fin = cleaned_data.get("fecha_fin")

        if fecha_inicio and fecha_fin:
            if fecha_fin < fecha_inicio:
                self.add_error(
                    "fecha_fin",
                    "La fecha de término no puede ser "
                    "anterior a la fecha de inicio."
                )

        if periodo:
            if periodo.cerrado:
                self.add_error(
                    "periodo",
                    "No se pueden agregar detalles "
                    "a un período cerrado."
                )

            if fecha_inicio:
                if fecha_inicio < periodo.fecha_inicio:
                    self.add_error(
                        "fecha_inicio",
                        "La fecha de inicio del detalle "
                        "no puede ser anterior a la "
                        "del período principal."
                    )

            if fecha_fin:
                if fecha_fin > periodo.fecha_fin:
                    self.add_error(
                        "fecha_fin",
                        "La fecha de término del detalle "
                        "no puede superar la fecha "
                        "de término del período principal."
                    )

        return cleaned_data


# ============================================================
# FORMULARIO 4: GESTIÓN DE METAS
# ============================================================

class MetaForm(forms.ModelForm):

    class Meta:
        model = Meta

        fields = [
            "codigo",
            "nombre",
            "descripcion",
            "periodo",
            "actividad",
            "valor_objetivo",
            "ponderacion",
            "activo",
        ]

        widgets = {
            "codigo": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Ej: META-001",
            }),

            "nombre": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Ej: Operativos de limpieza",
            }),

            "descripcion": forms.Textarea(attrs={
                "class": "form-control",
                "rows": 3,
                "placeholder": "Descripción de la meta",
            }),

            "periodo": forms.Select(attrs={
                "class": "form-select",
            }),

            "actividad": forms.Select(attrs={
                "class": "form-select",
            }),

            "valor_objetivo": forms.NumberInput(attrs={
                "class": "form-control",
                "min": "0.01",
                "step": "0.01",
                "placeholder": "Ej: 100",
            }),

            "ponderacion": forms.NumberInput(attrs={
                "class": "form-control",
                "min": "0",
                "max": "100",
                "step": "0.01",
                "placeholder": "Ej: 25",
            }),

            "activo": forms.CheckboxInput(attrs={
                "class": "form-check-input",
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Mostrar períodos abiertos.
        self.fields["periodo"].queryset = (
            Periodo.objects.filter(cerrado=False)
        )

        self.fields["periodo"].empty_label = (
            "Seleccione un período"
        )

        # Mostrar actividades activas.
        self.fields["actividad"].queryset = (
            CatalogoActividad.objects.filter(activo=True)
        )

        self.fields["actividad"].empty_label = (
            "Seleccione una actividad"
        )

    def clean_codigo(self):
        codigo = self.cleaned_data["codigo"].strip().upper()

        if Meta.objects.exclude(
            pk=self.instance.pk
        ).filter(
            codigo__iexact=codigo
        ).exists():
            raise forms.ValidationError(
                "Ya existe una meta con este código."
            )

        return codigo

    def clean(self):
        cleaned_data = super().clean()

        periodo = cleaned_data.get("periodo")
        actividad = cleaned_data.get("actividad")
        valor_objetivo = cleaned_data.get("valor_objetivo")
        ponderacion = cleaned_data.get("ponderacion")

        if periodo and periodo.cerrado:
            self.add_error(
                "periodo",
                "No se pueden registrar metas "
                "en períodos cerrados."
            )

        if actividad and not actividad.activo:
            self.add_error(
                "actividad",
                "No se pueden asignar metas "
                "a actividades inactivas."
            )

        if valor_objetivo is not None:
            if valor_objetivo <= 0:
                self.add_error(
                    "valor_objetivo",
                    "El valor objetivo debe ser "
                    "mayor que cero."
                )

        if ponderacion is not None:
            if ponderacion < 0 or ponderacion > 100:
                self.add_error(
                    "ponderacion",
                    "La ponderación debe estar "
                    "entre 0 y 100."
                )

        return cleaned_data
