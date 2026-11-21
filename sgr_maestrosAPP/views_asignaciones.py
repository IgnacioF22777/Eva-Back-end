"""
Asignación de metas por funcionario y trimestre (pauta Eva 3, Actividad 1
y 2): cantidad exigida y ponderación individuales, separadas del catálogo
de metas por cargo.

El Administrador asigna a cualquier funcionario; el Supervisor (delegado),
solo a los funcionarios de su delegación.
"""
from decimal import Decimal

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from seguridadAPP.models import PerfilUsuario, normalizar_rut
from tubo_gestionAPP.ambito import delegacion_id_de, es_global

from .models import AsignacionMeta, Meta, Periodo, metas_del_funcionario


def funcionarios_visibles(usuario):
    perfiles = PerfilUsuario.objects.filter(usuario__is_active=True).select_related(
        "usuario", "cargo", "delegacion"
    )
    if es_global(usuario):
        return perfiles
    propia = delegacion_id_de(usuario)
    return perfiles.filter(delegacion_id=propia) if propia else perfiles.none()


def nombre_funcionario(perfil):
    nombre = perfil.usuario.get_full_name() or perfil.usuario.username
    cargo = perfil.cargo.nombre if perfil.cargo_id else "sin cargo"
    return f"{nombre} ({cargo})"


def verificar_ambito(usuario, asignacion):
    if not funcionarios_visibles(usuario).filter(pk=asignacion.funcionario_id).exists():
        raise PermissionDenied(
            "El funcionario pertenece a otra delegación: solo puede asignar "
            "metas a los funcionarios de su delegación."
        )


class AsignacionMetaForm(forms.ModelForm):

    class Meta:
        model = AsignacionMeta
        fields = ["meta", "funcionario", "cantidad_exigida", "ponderacion", "observacion"]
        widgets = {
            "meta": forms.Select(attrs={"class": "form-select"}),
            "funcionario": forms.Select(attrs={"class": "form-select"}),
            "cantidad_exigida": forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": "0.01"}),
            "ponderacion": forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": "0", "max": "100"}),
            "observacion": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
        }

    def __init__(self, *args, usuario=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["meta"].queryset = (
            Meta.objects.filter(activo=True, periodo__cerrado=False)
            .select_related("periodo", "cargo")
            .order_by("periodo__codigo", "codigo")
        )
        self.fields["meta"].label_from_instance = lambda m: (
            f"{m.periodo.codigo} · {m.codigo} - {m.nombre} "
            f"({m.cargo.nombre if m.cargo_id else 'general'}; ref. {m.valor_objetivo} / {m.ponderacion}%)"
        )
        self.fields["funcionario"].queryset = funcionarios_visibles(usuario).order_by(
            "usuario__first_name", "usuario__last_name"
        )
        self.fields["funcionario"].label_from_instance = nombre_funcionario

        # Al editar no se cambia de meta ni de funcionario: se da de baja y
        # se crea otra asignación.
        if self.instance.pk:
            self.fields["meta"].disabled = True
            self.fields["funcionario"].disabled = True


@login_required
@permission_required("sgr_maestrosAPP.view_asignacionmeta", raise_exception=True)
def asignacion_lista(request):
    busqueda = request.GET.get("q", "").strip()
    estado = request.GET.get("estado", "activos")
    periodo_id = request.GET.get("periodo", "")

    funcionarios = funcionarios_visibles(request.user)
    asignaciones = AsignacionMeta.objects.filter(funcionario__in=funcionarios).select_related(
        "meta__periodo", "meta__cargo", "meta__actividad",
        "funcionario__usuario", "funcionario__cargo", "funcionario__delegacion",
    )

    periodo = None
    if periodo_id.isdigit():
        periodo = Periodo.objects.filter(pk=int(periodo_id)).first()
    if periodo:
        asignaciones = asignaciones.filter(meta__periodo=periodo)
    else:
        periodo_id = ""

    if estado == "activos":
        asignaciones = asignaciones.filter(activo=True)
    elif estado == "inactivos":
        asignaciones = asignaciones.filter(activo=False)
    else:
        estado = "todos"

    if busqueda:
        asignaciones = asignaciones.filter(
            Q(funcionario__usuario__first_name__icontains=busqueda)
            | Q(funcionario__usuario__last_name__icontains=busqueda)
            | Q(funcionario__rut__icontains=normalizar_rut(busqueda))
            | Q(meta__codigo__icontains=busqueda)
            | Q(meta__nombre__icontains=busqueda)
        )

    # Resumen por funcionario del período elegido: suma de ponderaciones
    # efectivas (metas del cargo + asignaciones individuales).
    resumen = []
    if periodo:
        for perfil in funcionarios.order_by("usuario__first_name"):
            metas = metas_del_funcionario(perfil, periodo)
            if metas:
                total = sum((m.ponderacion for m in metas), Decimal("0"))
                resumen.append({
                    "funcionario": nombre_funcionario(perfil),
                    "metas": len(metas),
                    "individuales": sum(1 for m in metas if m.individual),
                    "total": total,
                    "completo": total == 100,
                })

    pagina = Paginator(
        asignaciones.order_by("meta__periodo__codigo", "funcionario__usuario__first_name", "meta__codigo"),
        50,
    ).get_page(request.GET.get("pagina"))
    parametros = request.GET.copy()
    parametros.pop("pagina", None)

    return render(request, "sgr_maestros/asignacion_lista.html", {
        "pagina": pagina,
        "parametros": parametros.urlencode(),
        "busqueda": busqueda,
        "estado": estado,
        "periodo_id": periodo_id,
        "periodos": Periodo.objects.order_by("-fecha_inicio"),
        "resumen": resumen,
    })


def guardar(request, instancia, titulo, mensaje):
    form = AsignacionMetaForm(request.POST or None, instance=instancia, usuario=request.user)
    if request.method == "POST" and form.is_valid():
        asignacion = form.save(commit=False)
        verificar_ambito(request.user, asignacion)
        asignacion.save()
        messages.success(request, mensaje)
        return redirect("sgr_maestros:asignacion_lista")

    return render(request, "sgr_maestros/asignacion_form.html", {"form": form, "titulo": titulo})


@login_required
@permission_required("sgr_maestrosAPP.add_asignacionmeta", raise_exception=True)
def asignacion_crear(request):
    return guardar(request, None, "Asignar meta a funcionario", "Meta asignada correctamente.")


@login_required
@permission_required("sgr_maestrosAPP.change_asignacionmeta", raise_exception=True)
def asignacion_editar(request, pk):
    asignacion = get_object_or_404(AsignacionMeta.objects.select_related("meta__periodo"), pk=pk)
    verificar_ambito(request.user, asignacion)
    if asignacion.meta.periodo.cerrado:
        messages.error(request, "El período está cerrado: la asignación no se puede modificar.")
        return redirect("sgr_maestros:asignacion_lista")
    return guardar(request, asignacion, f"Editar asignación: {asignacion}", "Asignación actualizada correctamente.")


@login_required
@permission_required("sgr_maestrosAPP.delete_asignacionmeta", raise_exception=True)
@require_POST
def asignacion_cambiar_estado(request, pk):
    asignacion = get_object_or_404(AsignacionMeta.objects.select_related("meta__periodo"), pk=pk)
    verificar_ambito(request.user, asignacion)

    if asignacion.meta.periodo.cerrado:
        messages.error(request, "El período está cerrado: la asignación no se puede modificar.")
        return redirect("sgr_maestros:asignacion_lista")

    asignacion.activo = not asignacion.activo
    if asignacion.activo:
        # Al reactivar se vuelven a validar el 100% y los duplicados.
        try:
            asignacion.full_clean()
        except ValidationError as error:
            messages.error(request, "No se puede reactivar: " + " ".join(error.messages))
            return redirect("sgr_maestros:asignacion_lista")

    asignacion.save(update_fields=["activo"])
    messages.success(
        request,
        "Asignación reactivada." if asignacion.activo
        else "Asignación dada de baja: el funcionario vuelve a la meta de su cargo.",
    )
    return redirect("sgr_maestros:asignacion_lista")
