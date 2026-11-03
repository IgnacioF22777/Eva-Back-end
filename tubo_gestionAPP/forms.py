from django import forms
from django.core.exceptions import ValidationError

from django.template.defaultfilters import filesizeformat

from delegacionesAPP.models import Delegacion, Servicio

from . import adjuntos as reglas_adjuntos
from .ambito import delegacion_id_de, es_global
from .models import AsignacionCompromiso, Compromiso, RegistroAvance


class EntradaVariosArchivos(forms.FileInput):
    """Input de archivo que permite seleccionar varios a la vez."""

    allow_multiple_selected = True


class CampoVariosArchivos(forms.FileField):
    """
    Campo que devuelve una lista de archivos (vacía si no se adjunta
    ninguno). Cada archivo se valida por separado y luego el conjunto.
    """

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("widget", EntradaVariosArchivos())
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        if not data:
            data = []
        elif not isinstance(data, (list, tuple)):
            data = [data]

        archivos = [super(CampoVariosArchivos, self).clean(item, initial)
                    for item in data]
        archivos = [archivo for archivo in archivos if archivo]

        errores = []

        for archivo in archivos:
            try:
                reglas_adjuntos.validar_archivo_adjunto(archivo)
            except ValidationError as error:
                errores.extend(error.messages)

        try:
            reglas_adjuntos.validar_conjunto_adjuntos(archivos)
        except ValidationError as error:
            errores.extend(error.messages)

        if errores:
            raise ValidationError(errores)

        return archivos


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

    def __init__(self, *args, usuario=None, **kwargs):
        super().__init__(*args, **kwargs)

        delegaciones = Delegacion.objects.filter(
            activo=True
        ).order_by("nombre")

        servicios = Servicio.objects.filter(
            activo=True,
            delegacion__activo=True,
        ).select_related("delegacion").order_by(
            "delegacion__nombre", "nombre"
        )

        # Ámbito territorial: sin visión global solo se ofrece la
        # delegación propia (y sus servicios). Una delegación ajena
        # enviada a mano queda como "opción no válida".
        if usuario is not None and not es_global(usuario):
            propia = delegacion_id_de(usuario)
            delegaciones = delegaciones.filter(pk=propia)
            servicios = servicios.filter(delegacion_id=propia)

        self.fields["delegacion"].queryset = delegaciones

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

    adjuntos = CampoVariosArchivos(
        label="Archivos de respaldo (opcional)",
        required=False,
        help_text=(
            f"Cualquier tipo de archivo: fotografías, PDF, planillas, "
            f"documentos, etc. Máximo {reglas_adjuntos.MAX_ARCHIVOS} archivos, "
            f"{filesizeformat(reglas_adjuntos.MAX_BYTES_POR_ARCHIVO)} por archivo "
            f"y {filesizeformat(reglas_adjuntos.MAX_BYTES_TOTAL)} en total. No se "
            f"aceptan ejecutables ni scripts."
        ),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Datos que usa el navegador para avisar antes de enviar.
        self.fields["adjuntos"].widget.attrs.update({
            "class": "form-control",
            "multiple": True,
            "data-max-archivos": reglas_adjuntos.MAX_ARCHIVOS,
            "data-max-bytes-archivo": reglas_adjuntos.MAX_BYTES_POR_ARCHIVO,
            "data-max-bytes-total": reglas_adjuntos.MAX_BYTES_TOTAL,
        })

    def clean_evidencia(self):
        evidencia = (self.cleaned_data.get("evidencia") or "").strip()

        if not evidencia:
            raise forms.ValidationError(
                "La evidencia del avance es obligatoria."
            )

        return evidencia

    def clean_observacion(self):
        return (self.cleaned_data.get("observacion") or "").strip()
