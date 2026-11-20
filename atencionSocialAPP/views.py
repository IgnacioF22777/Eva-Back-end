from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from tubo_gestionAPP.ambito import SIN_DELEGACION, delegacion_id_de, es_global

from .forms import AtencionSocialForm
from .models import TIPOS, AtencionSocial


POR_PAGINA = 25


def atenciones_visibles(usuario):
    """Cada funcionario ve las atenciones de su delegación; el Administrador, todas."""
    atenciones = AtencionSocial.objects.select_related("delegacion", "registrada_por")
    if es_global(usuario):
        return atenciones
    propia = delegacion_id_de(usuario)
    return atenciones.filter(delegacion_id=propia) if propia else atenciones.none()


def obtener_atencion(usuario, pk):
    atencion = get_object_or_404(AtencionSocial, pk=pk)
    if not es_global(usuario) and atencion.delegacion_id != delegacion_id_de(usuario):
        raise PermissionDenied(
            "La atención pertenece a otra delegación: su perfil solo puede "
            "operar las atenciones de su delegación."
        )
    return atencion


def exigir_delegacion(usuario):
    if not es_global(usuario) and delegacion_id_de(usuario) is None:
        raise PermissionDenied(SIN_DELEGACION)


@login_required
@permission_required("atencionSocialAPP.view_atencionsocial", raise_exception=True)
def atencion_lista(request):
    busqueda = request.GET.get("q", "").strip()
    tipo = request.GET.get("tipo", "")
    vigencia = request.GET.get("vigencia", "activos")

    visibles = atenciones_visibles(request.user)
    atenciones = visibles

    if busqueda:
        atenciones = atenciones.filter(
            Q(nombre_vecino__icontains=busqueda) | Q(derivada_a__icontains=busqueda)
            | Q(detalle__icontains=busqueda)
        )
    if tipo in dict(TIPOS):
        atenciones = atenciones.filter(tipo=tipo)
    else:
        tipo = ""
    if vigencia == "activos":
        atenciones = atenciones.filter(activo=True)
    elif vigencia == "inactivos":
        atenciones = atenciones.filter(activo=False)
    else:
        vigencia = "todos"

    # Resumen por tipo de las atenciones vigentes del ámbito del usuario.
    conteo = dict(
        visibles.filter(activo=True).values_list("tipo").annotate(total=Count("id"))
    )
    resumen = [(valor, etiqueta, conteo.get(valor, 0)) for valor, etiqueta in TIPOS]

    pagina = Paginator(atenciones, POR_PAGINA).get_page(request.GET.get("pagina"))
    parametros = request.GET.copy()
    parametros.pop("pagina", None)

    return render(request, "atencion_social/atencion_lista.html", {
        "pagina": pagina,
        "total_filtradas": pagina.paginator.count,
        "busqueda": busqueda,
        "tipo": tipo,
        "vigencia": vigencia,
        "tipos": TIPOS,
        "resumen": resumen,
        "parametros": parametros.urlencode(),
    })


@login_required
@permission_required("atencionSocialAPP.add_atencionsocial", raise_exception=True)
def atencion_crear(request):
    exigir_delegacion(request.user)
    form = AtencionSocialForm(request.POST or None, usuario=request.user)
    if request.method == "POST" and form.is_valid():
        atencion = form.save(commit=False)
        atencion.registrada_por = request.user
        atencion.save()
        messages.success(request, "Atención social registrada correctamente.")
        return redirect("atencion_social:atencion_lista")
    return render(request, "atencion_social/atencion_form.html",
                  {"form": form, "titulo": "Registrar atención social"})


@login_required
@permission_required("atencionSocialAPP.change_atencionsocial", raise_exception=True)
def atencion_editar(request, pk):
    atencion = obtener_atencion(request.user, pk)
    form = AtencionSocialForm(request.POST or None, instance=atencion, usuario=request.user)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Atención social actualizada correctamente.")
        return redirect("atencion_social:atencion_lista")
    return render(request, "atencion_social/atencion_form.html",
                  {"form": form, "titulo": "Editar atención social", "atencion": atencion})


@login_required
@permission_required("atencionSocialAPP.delete_atencionsocial", raise_exception=True)
@require_POST
def atencion_cambiar_estado(request, pk):
    """Baja lógica: el registro se conserva para la trazabilidad."""
    atencion = obtener_atencion(request.user, pk)
    atencion.activo = not atencion.activo
    atencion.save(update_fields=["activo"])
    accion = "reactivada" if atencion.activo else "dada de baja"
    messages.success(request, f"Atención social {accion}.")
    return redirect("atencion_social:atencion_lista")
