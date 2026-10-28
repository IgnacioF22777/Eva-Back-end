from django import forms

from .models import Delegacion, Servicio


class DelegacionForm(forms.ModelForm):
    class Meta:
        model = Delegacion

        fields = [
            "nombre",
            "direccion",
            "encargado",
            "email",
            "telefono",
            "celular",
        ]

        widgets = {
            "nombre": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Ej: Delegación Centro",
                "autofocus": True,
            }),
            "direccion": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Calle, número, sector",
            }),
            "encargado": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Nombre del responsable",
            }),
            "email": forms.EmailInput(attrs={
                "class": "form-control",
                "placeholder": "delegacion@laserena.cl",
            }),
            "telefono": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "51 2 000 000",
            }),
            "celular": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "+56 9 0000 0000",
            }),
        }

    def clean_nombre(self):
        nombre = (self.cleaned_data.get("nombre") or "").strip()

        if not nombre:
            raise forms.ValidationError(
                "El nombre de la delegación es obligatorio."
            )

        existentes = Delegacion.objects.filter(nombre__iexact=nombre)

        if self.instance.pk:
            existentes = existentes.exclude(pk=self.instance.pk)

            # Si el nombre no cambió, se permite guardar aunque existan
            # registros históricos duplicados.
            if self.instance.nombre.strip().lower() == nombre.lower():
                return nombre

        if existentes.filter(activo=True).exists():
            raise forms.ValidationError(
                "Ya existe una delegación activa con este nombre."
            )

        return nombre

    def clean_email(self):
        return (self.cleaned_data.get("email") or "").strip().lower()


class ServicioForm(forms.ModelForm):
    class Meta:
        model = Servicio

        fields = ["nombre"]

        widgets = {
            "nombre": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Ej: Retiro de escombros",
                "autofocus": True,
            }),
        }

    def __init__(self, *args, delegacion=None, **kwargs):
        self.delegacion = delegacion
        super().__init__(*args, **kwargs)

    def clean_nombre(self):
        nombre = (self.cleaned_data.get("nombre") or "").strip()

        if not nombre:
            raise forms.ValidationError(
                "El nombre del servicio es obligatorio."
            )

        existentes = Servicio.objects.filter(
            delegacion=self.delegacion,
            nombre__iexact=nombre,
        )

        if self.instance.pk:
            existentes = existentes.exclude(pk=self.instance.pk)

            # Renombrar a un servicio que ya existe (activo o inactivo)
            # produciría dos registros con el mismo nombre.
            if existentes.exists():
                raise forms.ValidationError(
                    "Ya existe un servicio con este nombre en la delegación."
                )
        elif existentes.filter(activo=True).exists():
            raise forms.ValidationError(
                "Ya existe un servicio activo con este nombre en la delegación."
            )

        return nombre
