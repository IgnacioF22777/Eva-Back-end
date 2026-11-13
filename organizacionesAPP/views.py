from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from delegacionesAPP.models import Delegacion
from tubo_gestionAPP.ambito import delegacion_id_de, es_global

from .forms import OrganizacionForm
from .models import OrganizacionComunitaria


POR_PAGINA = 50


def volver_al_listado(request):
    """Vuelve a la página del listado de origen, solo si es de este sitio."""
    destino = request.POST.get("volver", "")
    if destino and url_has_allowed_host_and_scheme(
        destino, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return redirect(destino)
    return redirect("organizaciones:organizacion_lista")


def verificar_ambito(usuario, organizacion):
    """Sin visión global solo se modifican organizaciones de la delegación propia."""
    if es_global(usuario):
        return
    if organizacion.delegacion_id is None or organizacion.delegacion_id != delegacion_id_de(usuario):
        raise PermissionDenied(
            "La organización pertenece a otra delegación: su perfil solo puede "
            "modificar las organizaciones de su delegación."
        )


# ============================================================
# MANTENEDOR: ORGANIZACIONES COMUNITARIAS
# ============================================================

@login_required
@permission_required("organizacionesAPP.view_organizacioncomunitaria", raise_exception=True)
def organizacion_lista(request):
    busqueda = request.GET.get("q", "").strip()
    tipo = request.GET.get("tipo", "")
    estado = request.GET.get("estado", "activos")
    verificacion = request.GET.get("verificacion", "")

    # Ámbito: solo el Administrador elige delegación en el filtro. El resto
    # ve siempre la suya y se ignora lo que venga en la URL (?delegacion=).
    vision_global = es_global(request.user)
    visibles = OrganizacionComunitaria.objects.select_related("delegacion")

    if vision_global:
        delegacion = request.GET.get("delegacion", "")
        delegaciones = Delegacion.objects.order_by("nombre")
    else:
        propia = delegacion_id_de(request.user)
        # Sin delegación asignada no se ve ninguna organización.
        visibles = visibles.filter(delegacion_id=propia) if propia else visibles.none()
        delegacion = str(propia) if propia else ""
        delegaciones = Delegacion.objects.filter(pk=propia)

    organizaciones = visibles

    if busqueda:
        organizaciones = organizaciones.filter(
            Q(nombre__icontains=busqueda)
            | Q(numero_registro__icontains=busqueda)
            | Q(domicilio__icontains=busqueda)
        )

    tipos_validos = dict(OrganizacionComunitaria.TIPOS)
    if tipo in tipos_validos:
        organizaciones = organizaciones.filter(tipo=tipo)
    else:
        tipo = ""

    # El filtro de la URL solo se aplica con visión global.
    if vision_global:
        if delegacion == "sin":
            organizaciones = organizaciones.filter(delegacion__isnull=True)
        elif delegacion.isdigit():
            organizaciones = organizaciones.filter(delegacion_id=int(delegacion))
        else:
            delegacion = ""

    if verificacion == "si":
        organizaciones = organizaciones.filter(verificada=True)
    elif verificacion == "no":
        organizaciones = organizaciones.filter(verificada=False)
    else:
        verificacion = ""

    if estado == "activos":
        organizaciones = organizaciones.filter(activo=True)
    elif estado == "inactivos":
        organizaciones = organizaciones.filter(activo=False)
    else:
        estado = "todos"

    pagina = Paginator(organizaciones.order_by("nombre"), POR_PAGINA).get_page(
        request.GET.get("pagina")
    )

    parametros = request.GET.copy()
    parametros.pop("pagina", None)
    parametros["delegacion"] = delegacion

    # Los contadores también respetan el ámbito del usuario.
    todas = visibles
    return render(
        request,
        "organizaciones/organizacion_lista.html",
        {
            "pagina": pagina,
            "total_filtradas": pagina.paginator.count,
            "busqueda": busqueda,
            "tipo": tipo,
            "delegacion": delegacion,
            "verificacion": verificacion,
            "estado": estado,
            "parametros": parametros.urlencode(),
            "tipos": OrganizacionComunitaria.TIPOS,
            "delegaciones": delegaciones,
            "vision_global": vision_global,
            "total_vigentes": todas.filter(activo=True).count(),
            "total_por_verificar": todas.filter(activo=True, verificada=False).count(),
            "total_sin_delegacion": todas.filter(activo=True, delegacion__isnull=True).count(),
        },
    )


@login_required
@permission_required("organizacionesAPP.add_organizacioncomunitaria", raise_exception=True)
def organizacion_crear(request):
    if request.method == "POST":
        form = OrganizacionForm(request.POST, usuario=request.user)

        if form.is_valid():
            organizacion = form.save()
            messages.success(
                request, f"Organización «{organizacion.nombre}» registrada correctamente."
            )
            return redirect("organizaciones:organizacion_lista")
    else:
        form = OrganizacionForm(usuario=request.user)

    return render(
        request,
        "organizaciones/organizacion_form.html",
        {"form": form, "titulo": "Registrar organización comunitaria"},
    )


@login_required
@permission_required("organizacionesAPP.change_organizacioncomunitaria", raise_exception=True)
def organizacion_editar(request, pk):
    organizacion = get_object_or_404(OrganizacionComunitaria, pk=pk)
    verificar_ambito(request.user, organizacion)

    if request.method == "POST":
        form = OrganizacionForm(request.POST, instance=organizacion, usuario=request.user)

        if form.is_valid():
            form.save()
            messages.success(request, "Organización actualizada correctamente.")
            return redirect("organizaciones:organizacion_lista")
    else:
        form = OrganizacionForm(instance=organizacion, usuario=request.user)

    return render(
        request,
        "organizaciones/organizacion_form.html",
        {
            "form": form,
            "titulo": f"Editar organización: {organizacion.nombre}",
            "organizacion": organizacion,
        },
    )


@login_required
@permission_required("organizacionesAPP.change_organizacioncomunitaria", raise_exception=True)
@require_POST
def organizacion_verificar(request, pk):
    organizacion = get_object_or_404(OrganizacionComunitaria, pk=pk)
    verificar_ambito(request.user, organizacion)

    organizacion.verificada = not organizacion.verificada
    organizacion.save(update_fields=["verificada"])

    messages.success(
        request,
        "Organización marcada como verificada." if organizacion.verificada
        else "La organización volvió a quedar pendiente de verificación.",
    )
    return volver_al_listado(request)


@login_required
@permission_required("organizacionesAPP.delete_organizacioncomunitaria", raise_exception=True)
@require_POST
def organizacion_cambiar_estado(request, pk):
    organizacion = get_object_or_404(OrganizacionComunitaria, pk=pk)
    verificar_ambito(request.user, organizacion)

    # Baja lógica: la organización se conserva como historial.
    organizacion.activo = not organizacion.activo
    organizacion.save(update_fields=["activo"])

    messages.success(
        request,
        "Organización reactivada." if organizacion.activo
        else "Organización dada de baja. Puede reactivarla cuando sea necesario.",
    )
    return volver_al_listado(request)
