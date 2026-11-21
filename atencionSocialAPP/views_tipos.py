"""
Mantenedor de tipos y subtipos de atención social (pauta Eva 3: CRUD con
validaciones sobre «tipos y subtipos de atención»).

Los códigos no se modifican una vez creados porque las atenciones guardan
el código. La eliminación es lógica: un tipo o subtipo dado de baja deja
de ofrecerse en registros nuevos, pero los registros antiguos lo conservan.
"""
from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .models import AtencionSocial, SubtipoAtencion, TipoAtencion


class TipoAtencionForm(forms.ModelForm):

    class Meta:
        model = TipoAtencion
        fields = ["codigo", "nombre", "exige_destino"]
        widgets = {
            "codigo": forms.TextInput(attrs={"class": "form-control", "placeholder": "Ej: VISITA", "autofocus": True}),
            "nombre": forms.TextInput(attrs={"class": "form-control", "placeholder": "Ej: Visita domiciliaria"}),
            "exige_destino": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def __init__(self, *args, usuario=None, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields["codigo"].disabled = True

    def clean_codigo(self):
        codigo = "_".join((self.cleaned_data.get("codigo") or "").upper().split())
        if TipoAtencion.objects.filter(codigo__iexact=codigo).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("Ya existe un tipo con este código.")
        return codigo


class SubtipoAtencionForm(forms.ModelForm):

    class Meta:
        model = SubtipoAtencion
        fields = ["tipo", "codigo", "nombre"]
        widgets = {
            "tipo": forms.Select(attrs={"class": "form-select"}),
            "codigo": forms.TextInput(attrs={"class": "form-control", "placeholder": "Ej: BONO_INVIERNO"}),
            "nombre": forms.TextInput(attrs={"class": "form-control", "placeholder": "Ej: Bono de invierno"}),
        }

    def __init__(self, *args, usuario=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["tipo"].queryset = TipoAtencion.objects.filter(activo=True).order_by("nombre")
        if self.instance.pk:
            self.fields["codigo"].disabled = True
            self.fields["tipo"].disabled = True

    def clean_codigo(self):
        codigo = "_".join((self.cleaned_data.get("codigo") or "").upper().split())
        if SubtipoAtencion.objects.filter(codigo__iexact=codigo).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("Ya existe un subtipo con este código.")
        return codigo


LISTA = "atencion_social:tipo_lista"


def formulario(request, form_class, instancia, titulo, mensaje):
    form = form_class(request.POST or None, instance=instancia)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, mensaje)
        return redirect(LISTA)
    return render(request, "comunidad/formulario.html", {"form": form, "titulo": titulo, "lista": LISTA})


@login_required
@permission_required("atencionSocialAPP.view_tipoatencion", raise_exception=True)
def tipo_lista(request):
    busqueda = request.GET.get("q", "").strip()
    estado = request.GET.get("estado", "activos")

    tipos = TipoAtencion.objects.prefetch_related("subtipos")
    if estado == "activos":
        tipos = tipos.filter(activo=True)
    elif estado == "inactivos":
        tipos = tipos.filter(activo=False)
    else:
        estado = "todos"
    if busqueda:
        tipos = tipos.filter(
            Q(nombre__icontains=busqueda) | Q(codigo__icontains=busqueda)
            | Q(subtipos__nombre__icontains=busqueda) | Q(subtipos__codigo__icontains=busqueda)
        ).distinct()

    usos_tipo = dict(AtencionSocial.objects.values_list("tipo").annotate(total=Count("id")))
    usos_subtipo = dict(
        AtencionSocial.objects.exclude(subtipo="").values_list("subtipo").annotate(total=Count("id"))
    )

    filas = [
        {
            "tipo": tipo,
            "usos": usos_tipo.get(tipo.codigo, 0),
            "subtipos": [
                {"subtipo": s, "usos": usos_subtipo.get(s.codigo, 0)}
                for s in sorted(tipo.subtipos.all(), key=lambda s: (not s.activo, s.nombre))
            ],
        }
        for tipo in tipos.order_by("-activo", "nombre")
    ]
    return render(request, "atencion_social/tipo_lista.html", {
        "filas": filas, "busqueda": busqueda, "estado": estado,
    })


@login_required
@permission_required("atencionSocialAPP.add_tipoatencion", raise_exception=True)
def tipo_crear(request):
    return formulario(request, TipoAtencionForm, None, "Nuevo tipo de atención social", "Tipo de atención creado correctamente.")


@login_required
@permission_required("atencionSocialAPP.change_tipoatencion", raise_exception=True)
def tipo_editar(request, pk):
    tipo = get_object_or_404(TipoAtencion, pk=pk)
    return formulario(request, TipoAtencionForm, tipo, f"Editar tipo: {tipo.nombre}", "Tipo de atención actualizado.")


@login_required
@permission_required("atencionSocialAPP.delete_tipoatencion", raise_exception=True)
@require_POST
def tipo_cambiar_estado(request, pk):
    tipo = get_object_or_404(TipoAtencion, pk=pk)
    if tipo.activo and tipo.subtipos.filter(activo=True).exists():
        messages.error(request, "No se puede dar de baja: el tipo tiene subtipos vigentes. Délos de baja primero.")
        return redirect(LISTA)
    tipo.activo = not tipo.activo
    tipo.save(update_fields=["activo"])
    messages.success(
        request,
        "Tipo reactivado." if tipo.activo
        else "Tipo dado de baja: ya no se ofrece en atenciones nuevas; las existentes lo conservan.",
    )
    return redirect(LISTA)


@login_required
@permission_required("atencionSocialAPP.add_subtipoatencion", raise_exception=True)
def subtipo_crear(request):
    instancia = None
    tipo = request.GET.get("tipo", "")
    if request.method == "GET" and tipo.isdigit():
        instancia = SubtipoAtencion(tipo=TipoAtencion.objects.filter(pk=int(tipo), activo=True).first())
    return formulario(request, SubtipoAtencionForm, instancia, "Nuevo subtipo de atención social", "Subtipo creado correctamente.")


@login_required
@permission_required("atencionSocialAPP.change_subtipoatencion", raise_exception=True)
def subtipo_editar(request, pk):
    subtipo = get_object_or_404(SubtipoAtencion, pk=pk)
    return formulario(request, SubtipoAtencionForm, subtipo, f"Editar subtipo: {subtipo.nombre}", "Subtipo actualizado.")


@login_required
@permission_required("atencionSocialAPP.delete_subtipoatencion", raise_exception=True)
@require_POST
def subtipo_cambiar_estado(request, pk):
    subtipo = get_object_or_404(SubtipoAtencion.objects.select_related("tipo"), pk=pk)
    if not subtipo.activo and not subtipo.tipo.activo:
        messages.error(request, "Reactive primero el tipo de atención al que pertenece.")
        return redirect(LISTA)
    subtipo.activo = not subtipo.activo
    subtipo.save(update_fields=["activo"])
    messages.success(request, "Subtipo reactivado." if subtipo.activo else "Subtipo dado de baja.")
    return redirect(LISTA)
