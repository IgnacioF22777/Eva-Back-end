from django import forms
from django.contrib.auth import get_user_model

from delegacionesAPP.models import Delegacion
from organizacionesAPP.models import OrganizacionComunitaria
from tubo_gestionAPP.ambito import delegacion_id_de, es_global

from .models import Hito, MembresiaJunta, Territorio, Vecino


FECHA = {"class": "form-control", "type": "date"}


def delegaciones_permitidas(usuario):
    """Delegaciones que el usuario puede elegir según su ámbito."""
    delegaciones = Delegacion.objects.filter(activo=True).order_by("nombre")
    if usuario is not None and not es_global(usuario):
        delegaciones = delegaciones.filter(pk=delegacion_id_de(usuario))
    return delegaciones


class FormularioConAmbito(forms.ModelForm):
    """Limita el campo «delegacion» a las delegaciones del ámbito del usuario."""

    def __init__(self, *args, usuario=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.usuario = usuario
        self.delegaciones = delegaciones_permitidas(usuario)

        if "delegacion" in self.fields:
            self.fields["delegacion"].queryset = self.delegaciones
            if usuario is not None and not es_global(usuario):
                self.fields["delegacion"].empty_label = None


# ============================================================
# TERRITORIOS
# ============================================================

class TerritorioForm(FormularioConAmbito):

    class Meta:
        model = Territorio
        fields = ["nombre", "delegacion", "descripcion"]
        widgets = {
            "nombre": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Ej: Unidad vecinal 14 - Villa El Indio",
                "autofocus": True,
            }),
            "delegacion": forms.Select(attrs={"class": "form-select"}),
            "descripcion": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
        }


# ============================================================
# VECINOS
# ============================================================

class VecinoForm(FormularioConAmbito):

    class Meta:
        model = Vecino
        fields = ["rut", "nombre", "telefono", "correo", "direccion", "delegacion", "territorio"]
        labels = {"telefono": "Teléfono (9 dígitos)"}
        widgets = {
            "rut": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "12.345.678-5",
                "autofocus": True,
            }),
            "nombre": forms.TextInput(attrs={"class": "form-control"}),
            "telefono": forms.TextInput(attrs={"class": "form-control", "placeholder": "912345678"}),
            "correo": forms.EmailInput(attrs={"class": "form-control"}),
            "direccion": forms.TextInput(attrs={"class": "form-control"}),
            "delegacion": forms.Select(attrs={"class": "form-select"}),
            "territorio": forms.Select(attrs={"class": "form-select"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        territorios = Territorio.objects.filter(
            activo=True, delegacion__in=self.delegaciones
        ).select_related("delegacion")
        self.fields["territorio"].queryset = territorios
        self.fields["territorio"].empty_label = "Sin territorio"
        self.fields["territorio"].label_from_instance = (
            lambda t: f"{t.nombre} ({t.delegacion.nombre})"
        )

    def clean_rut(self):
        from seguridadAPP.models import normalizar_rut

        rut = normalizar_rut(self.cleaned_data.get("rut") or "")
        if Vecino.objects.filter(rut=rut).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("Ya existe un vecino registrado con este RUT.")
        return rut


# ============================================================
# MEMBRESÍAS EN JUNTAS DE VECINOS
# ============================================================

class MembresiaForm(forms.ModelForm):

    class Meta:
        model = MembresiaJunta
        fields = ["vecino", "tipo", "cargo", "fecha_inicio", "fecha_termino"]
        widgets = {
            "vecino": forms.Select(attrs={"class": "form-select"}),
            "tipo": forms.Select(attrs={"class": "form-select"}),
            "cargo": forms.Select(attrs={"class": "form-select"}),
            "fecha_inicio": forms.DateInput(format="%Y-%m-%d", attrs=FECHA),
            "fecha_termino": forms.DateInput(format="%Y-%m-%d", attrs=FECHA),
        }
        help_texts = {
            "cargo": "Solo para dirigentes. Presidente, vicepresidente, secretario y tesorero son únicos.",
            "fecha_termino": "Al indicar una fecha de término la membresía queda cerrada (historial).",
        }

    def __init__(self, *args, organizacion=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.organizacion = organizacion or self.instance.organizacion
        vecinos = Vecino.objects.filter(activo=True)
        if self.organizacion.delegacion_id:
            vecinos = vecinos.filter(delegacion_id=self.organizacion.delegacion_id)
        self.fields["vecino"].queryset = vecinos.order_by("nombre")
        self.fields["cargo"].choices = [("", "Sin cargo")] + MembresiaJunta.CARGOS

        # Al editar no se cambia de vecino: se cierra y se crea otra membresía.
        if self.instance.pk:
            self.fields["vecino"].disabled = True

    def clean(self):
        datos = super().clean()
        # Una membresía con fecha de término ya no está vigente.
        self.instance.activo = not bool(datos.get("fecha_termino"))
        return datos


# ============================================================
# HITOS
# ============================================================

class HitoForm(FormularioConAmbito):

    class Meta:
        model = Hito
        fields = [
            "nombre", "descripcion", "delegacion", "territorio", "organizacion",
            "responsable", "fecha_programada", "estado", "fecha_cumplimiento",
        ]
        widgets = {
            "nombre": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Ej: Operativo de salud en la sede vecinal",
                "autofocus": True,
            }),
            "descripcion": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "delegacion": forms.Select(attrs={"class": "form-select"}),
            "territorio": forms.Select(attrs={"class": "form-select"}),
            "organizacion": forms.Select(attrs={"class": "form-select"}),
            "responsable": forms.Select(attrs={"class": "form-select"}),
            "fecha_programada": forms.DateInput(format="%Y-%m-%d", attrs=FECHA),
            "estado": forms.Select(attrs={"class": "form-select"}),
            "fecha_cumplimiento": forms.DateInput(format="%Y-%m-%d", attrs=FECHA),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["territorio"].queryset = Territorio.objects.filter(
            activo=True, delegacion__in=self.delegaciones
        ).select_related("delegacion")
        self.fields["territorio"].empty_label = "Sin territorio"
        self.fields["territorio"].label_from_instance = (
            lambda t: f"{t.nombre} ({t.delegacion.nombre})"
        )

        self.fields["organizacion"].queryset = OrganizacionComunitaria.objects.filter(
            activo=True, delegacion__in=self.delegaciones
        ).order_by("nombre")
        self.fields["organizacion"].empty_label = "Ninguna"

        # Responsables: funcionarios activos de las delegaciones permitidas.
        User = get_user_model()
        self.fields["responsable"].queryset = (
            User.objects.filter(is_active=True, perfil__delegacion__in=self.delegaciones)
            .select_related("perfil__delegacion")
            .order_by("first_name", "last_name", "username")
        )
        self.fields["responsable"].label_from_instance = (
            lambda u: f"{u.get_full_name() or u.username} ({u.perfil.delegacion.nombre})"
        )
