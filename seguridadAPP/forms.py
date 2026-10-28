from django import forms
from django.contrib.auth import get_user_model, password_validation
from django.contrib.auth.forms import (
    AuthenticationForm,
    PasswordResetForm,
    SetPasswordForm,
)
from django.contrib.auth.models import Group, Permission
from django.core.exceptions import ValidationError

from delegacionesAPP.models import Delegacion
from tubo_gestionAPP.validadores import validar_rut_chileno

from .models import PerfilUsuario, normalizar_rut
from .roles import APPS_CON_PERMISOS, PERFILES


User = get_user_model()

ACCIONES = {
    "view": "Ver",
    "add": "Crear",
    "change": "Editar",
    "delete": "Eliminar",
}


# ============================================================
# FORMULARIO 1: INICIO DE SESIÓN (RUT O CORREO)
# ============================================================

class LoginForm(AuthenticationForm):

    username = forms.CharField(
        label="RUT o correo electrónico",
        max_length=254,
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "placeholder": "12.345.678-5 o nombre@laserena.cl",
            "autofocus": True,
            "autocomplete": "username",
        })
    )

    password = forms.CharField(
        label="Contraseña",
        strip=False,
        widget=forms.PasswordInput(attrs={
            "class": "form-control",
            "autocomplete": "current-password",
        })
    )

    recordar = forms.BooleanField(
        label="Recordar sesión",
        required=False,
        widget=forms.CheckboxInput(attrs={
            "class": "form-check-input",
        })
    )

    # Mensaje genérico: no revela si el RUT/correo existe o si la
    # cuenta está inactiva.
    error_messages = {
        "invalid_login": (
            "RUT/correo o contraseña incorrectos, "
            "o la cuenta se encuentra inactiva."
        ),
        "inactive": "Esta cuenta se encuentra inactiva.",
    }


# ============================================================
# FORMULARIO 2: USUARIOS (CREAR Y EDITAR)
# ============================================================

class UsuarioForm(forms.ModelForm):

    rut = forms.CharField(
        label="RUT",
        max_length=12,
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "placeholder": "Ej: 12.345.678-5",
        })
    )

    delegacion = forms.ModelChoiceField(
        label="Delegación",
        queryset=Delegacion.objects.all(),
        required=False,
        empty_label="Sin delegación asignada",
        widget=forms.Select(attrs={
            "class": "form-select",
        })
    )

    cargo = forms.CharField(
        label="Cargo",
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "placeholder": "Ej: Encargado territorial",
        })
    )

    groups = forms.ModelMultipleChoiceField(
        label="Roles",
        queryset=Group.objects.all(),
        widget=forms.CheckboxSelectMultiple(attrs={
            "class": "form-check-input",
        }),
        error_messages={
            "required": "Debe asignar al menos un rol.",
        }
    )

    password1 = forms.CharField(
        label="Contraseña",
        strip=False,
        widget=forms.PasswordInput(attrs={
            "class": "form-control",
            "autocomplete": "new-password",
        }),
        help_text=password_validation.password_validators_help_text_html()
    )

    password2 = forms.CharField(
        label="Confirmar contraseña",
        strip=False,
        widget=forms.PasswordInput(attrs={
            "class": "form-control",
            "autocomplete": "new-password",
        })
    )

    class Meta:
        model = User

        fields = [
            "first_name",
            "last_name",
            "email",
            "is_active",
        ]

        labels = {
            "first_name": "Nombres",
            "last_name": "Apellidos",
            "email": "Correo electrónico",
            "is_active": "Usuario activo",
        }

        widgets = {
            "first_name": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Nombres del funcionario",
            }),

            "last_name": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Apellidos del funcionario",
            }),

            "email": forms.EmailInput(attrs={
                "class": "form-control",
                "placeholder": "nombre@laserena.cl",
            }),

            "is_active": forms.CheckboxInput(attrs={
                "class": "form-check-input",
            }),
        }

    def __init__(self, *args, editor=None, **kwargs):
        super().__init__(*args, **kwargs)

        self.editor = editor
        self.es_nuevo = self.instance.pk is None

        self.fields["first_name"].required = True
        self.fields["last_name"].required = True
        self.fields["email"].required = True

        # Orden de los campos en pantalla.
        self.order_fields([
            "rut", "first_name", "last_name", "email",
            "delegacion", "cargo", "groups",
            "password1", "password2", "is_active",
        ])

        if self.es_nuevo:
            self.initial.setdefault("is_active", True)
        else:
            # La contraseña se cambia desde "Restablecer contraseña".
            del self.fields["password1"]
            del self.fields["password2"]

            self.initial["groups"] = self.instance.groups.all()

            perfil = getattr(self.instance, "perfil", None)

            if perfil:
                self.initial["rut"] = perfil.rut_formateado
                self.initial["delegacion"] = perfil.delegacion_id
                self.initial["cargo"] = perfil.cargo

        # Un usuario no puede cambiar sus propios roles ni desactivarse,
        # para evitar escalamiento de privilegios o bloquearse a sí mismo.
        if self.editando_a_si_mismo:
            self.fields["groups"].disabled = True
            self.fields["is_active"].disabled = True
            self.fields["groups"].help_text = (
                "No puede modificar sus propios roles."
            )

    @property
    def editando_a_si_mismo(self):
        return (
            not self.es_nuevo
            and self.editor is not None
            and self.editor.pk == self.instance.pk
        )

    def clean_rut(self):
        rut = normalizar_rut(self.cleaned_data["rut"])

        try:
            validar_rut_chileno(rut)
        except ValidationError as error:
            raise forms.ValidationError(error.messages)

        repetidos = PerfilUsuario.objects.filter(rut=rut)

        if not self.es_nuevo:
            repetidos = repetidos.exclude(usuario=self.instance)

        if repetidos.exists():
            raise forms.ValidationError(
                "Ya existe un usuario registrado con este RUT."
            )

        # El RUT también se usa como nombre de usuario interno.
        if User.objects.exclude(
            pk=self.instance.pk
        ).filter(
            username=rut
        ).exists():
            raise forms.ValidationError(
                "Ya existe un usuario registrado con este RUT."
            )

        return rut

    def clean_first_name(self):
        return self.cleaned_data["first_name"].strip()

    def clean_last_name(self):
        return self.cleaned_data["last_name"].strip()

    def clean_groups(self):
        grupos = self.cleaned_data["groups"]
        perfiles = {grupo.name for grupo in grupos} & set(PERFILES)

        if not perfiles:
            raise forms.ValidationError(
                "Debe asignar al menos uno de los perfiles: "
                + ", ".join(PERFILES) + "."
            )

        return grupos

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()

        if User.objects.exclude(
            pk=self.instance.pk
        ).filter(
            email__iexact=email
        ).exists():
            raise forms.ValidationError(
                "Ya existe un usuario registrado con este correo."
            )

        return email

    def clean(self):
        cleaned_data = super().clean()

        password1 = cleaned_data.get("password1")
        password2 = cleaned_data.get("password2")

        if self.es_nuevo and password1 and password2:
            if password1 != password2:
                self.add_error(
                    "password2",
                    "Las contraseñas no coinciden."
                )
            else:
                # Se valida con los AUTH_PASSWORD_VALIDATORS del proyecto.
                usuario_temporal = User(
                    username=cleaned_data.get("rut", ""),
                    first_name=cleaned_data.get("first_name", ""),
                    last_name=cleaned_data.get("last_name", ""),
                    email=cleaned_data.get("email", ""),
                )

                try:
                    password_validation.validate_password(
                        password1,
                        usuario_temporal
                    )
                except ValidationError as error:
                    self.add_error("password1", error)

        return cleaned_data

    def save(self, commit=True):
        usuario = super().save(commit=False)
        usuario.username = self.cleaned_data["rut"]

        if self.es_nuevo:
            usuario.set_password(self.cleaned_data["password1"])

        if commit:
            usuario.save()
            usuario.groups.set(self.cleaned_data["groups"])

            PerfilUsuario.objects.update_or_create(
                usuario=usuario,
                defaults={
                    "rut": self.cleaned_data["rut"],
                    "delegacion": self.cleaned_data.get("delegacion"),
                    "cargo": self.cleaned_data.get("cargo", "").strip(),
                }
            )

        return usuario


# ============================================================
# FORMULARIO 3: RESTABLECER CONTRASEÑA
# ============================================================

class RestablecerPasswordForm(SetPasswordForm):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["new_password1"].label = "Nueva contraseña"
        self.fields["new_password2"].label = "Confirmar nueva contraseña"

        for campo in self.fields.values():
            campo.widget.attrs["class"] = "form-control"


# ============================================================
# FORMULARIO 3B: SOLICITAR ENLACE DE RECUPERACIÓN
# ============================================================

class RecuperarPasswordForm(PasswordResetForm):
    """
    Django busca la cuenta por correo electrónico, no por RUT, así que
    el campo se rotula de forma explícita para evitar confusión.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["email"].label = "Correo institucional"
        self.fields["email"].widget = forms.EmailInput(attrs={
            "class": "form-control",
            "placeholder": "nombre@laserena.cl",
            "autocomplete": "email",
            "autofocus": True,
        })
        self.fields["email"].help_text = (
            "Le enviaremos un enlace para definir una nueva contraseña."
        )


# ============================================================
# FORMULARIO 4: ROLES (GRUPOS Y PERMISOS)
# ============================================================

class PermisosField(forms.ModelMultipleChoiceField):

    def label_from_instance(self, permiso):
        accion = permiso.codename.split("_")[0]
        return ACCIONES.get(accion, permiso.name)


class RolForm(forms.ModelForm):

    permissions = PermisosField(
        label="Permisos",
        queryset=Permission.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple(attrs={
            "class": "form-check-input",
        })
    )

    class Meta:
        model = Group

        fields = [
            "name",
            "permissions",
        ]

        labels = {
            "name": "Nombre del rol",
        }

        widgets = {
            "name": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Ej: Verificador",
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["permissions"].queryset = Permission.objects.filter(
            content_type__app_label__in=APPS_CON_PERMISOS
        ).exclude(
            # Los permisos sobre la tabla de permisos no se delegan.
            content_type__model="permission"
        ).select_related(
            "content_type"
        ).order_by(
            "content_type__app_label",
            "content_type__model",
            "codename",
        )

    def clean_name(self):
        nombre = self.cleaned_data["name"].strip()

        if Group.objects.exclude(
            pk=self.instance.pk
        ).filter(
            name__iexact=nombre
        ).exists():
            raise forms.ValidationError(
                "Ya existe un rol con este nombre."
            )

        return nombre

    def permisos_agrupados(self):
        """Agrupa las casillas de permisos por modelo para la plantilla."""
        grupos = {}

        for casilla in self["permissions"]:
            permiso = casilla.data["value"].instance
            modelo = permiso.content_type.model_class()

            if modelo is None:
                titulo = permiso.content_type.model
            elif modelo is Group:
                titulo = "Rol"
            else:
                titulo = str(modelo._meta.verbose_name).capitalize()

            grupos.setdefault(titulo, []).append(casilla)

        return grupos.items()
