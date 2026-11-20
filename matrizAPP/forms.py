from django import forms

from .ambito import funcionarios_gestionables
from .models import AjusteDesempeno, Ausencia


class FuncionarioChoiceField(forms.ModelChoiceField):
    """Muestra el nombre del funcionario y su cargo en vez del usuario."""

    def label_from_instance(self, usuario):
        nombre = usuario.get_full_name() or usuario.username
        cargo = getattr(getattr(usuario, "perfil", None), "cargo", None)
        return f"{nombre} ({cargo})" if cargo else nombre


class FormularioMatriz(forms.ModelForm):
    """
    Base común: el funcionario solo se elige entre los que el usuario
    puede gestionar. Los campos "registrado por" y "delegación" no están
    en el formulario: los pone el sistema, así que agregarlos al POST no
    tiene efecto.
    """

    def __init__(self, *args, usuario=None, **kwargs):
        super().__init__(*args, **kwargs)

        gestionables = funcionarios_gestionables(usuario)

        # Al editar, el funcionario no se cambia: se anula y se registra
        # de nuevo. Así no se puede "mover" un reclamo a otra persona.
        if self.instance.pk:
            gestionables = gestionables.filter(pk=self.instance.funcionario_id)

        self.fields["funcionario"] = FuncionarioChoiceField(
            queryset=gestionables,
            label="Funcionario",
            empty_label="Seleccione un funcionario",
            disabled=bool(self.instance.pk),
            widget=forms.Select(attrs={"class": "form-select"}),
        )


class AusenciaForm(FormularioMatriz):

    class Meta:
        model = Ausencia
        fields = ["funcionario", "tipo", "fecha_inicio", "fecha_fin", "observacion"]
        widgets = {
            "tipo": forms.Select(attrs={"class": "form-select"}),
            "fecha_inicio": forms.DateInput(
                format="%Y-%m-%d", attrs={"type": "date", "class": "form-control"}
            ),
            "fecha_fin": forms.DateInput(
                format="%Y-%m-%d", attrs={"type": "date", "class": "form-control"}
            ),
            "observacion": forms.Textarea(attrs={
                "class": "form-control",
                "rows": 3,
                "placeholder": "Ej.: licencia N° 123, folio del libro, etc.",
            }),
        }


class AjusteDesempenoForm(FormularioMatriz):

    class Meta:
        model = AjusteDesempeno
        fields = [
            "tipo",
            "funcionario",
            "fecha",
            "medio",
            "remitente_nombre",
            "remitente_contacto",
            "descripcion",
            "respaldo",
        ]
        widgets = {
            "tipo": forms.Select(attrs={"class": "form-select"}),
            "fecha": forms.DateInput(
                format="%Y-%m-%d", attrs={"type": "date", "class": "form-control"}
            ),
            "medio": forms.Select(attrs={"class": "form-select"}),
            "remitente_nombre": forms.TextInput(attrs={"class": "form-control"}),
            "remitente_contacto": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Teléfono o correo",
            }),
            "descripcion": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            # FileInput (sin casilla "borrar"): el respaldo es obligatorio.
            "respaldo": forms.FileInput(attrs={"class": "form-control"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Al editar se puede dejar el archivo que ya existe.
        if self.instance.pk and self.instance.respaldo:
            self.fields["respaldo"].required = False
            self.fields["respaldo"].help_text = (
                f"Actual: {self.instance.nombre_original}. "
                "Suba otro archivo solo si quiere reemplazarlo."
            )
