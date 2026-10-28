from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .forms import CompromisoForm
from .models import Compromiso


# ============================================================
# MANTENEDOR: COMPROMISOS DEL TUBO DE GESTIÓN
# ============================================================

@login_required
@permission_required("tubo_gestionAPP.view_compromiso", raise_exception=True)
def compromiso_lista(request):
    busqueda = request.GET.get("q", "").strip()
    estado = request.GET.get("estado", "")
    situacion = request.GET.get("situacion", "activos")

    compromisos = Compromiso.objects.select_related("delegacion").all()

    if busqueda:
        compromisos = compromisos.filter(
            Q(tarea__icontains=busqueda)
            | Q(delegacion__nombre__icontains=busqueda)
        )

    if estado in ("verde", "amarillo", "rojo"):
        compromisos = compromisos.filter(estado=estado)

    if situacion == "activos":
        compromisos = compromisos.filter(activo=True)
    elif situacion == "inactivos":
        compromisos = compromisos.filter(activo=False)

    resumen = {"verde": 0, "amarillo": 0, "rojo": 0}

    for fila in Compromiso.objects.filter(activo=True).values(
        "estado"
    ).annotate(total=Count("pk")):
        if fila["estado"] in resumen:
            resumen[fila["estado"]] = fila["total"]

    return render(
        request,
        "tubo_gestion/tablero_metas.html",
        {
            "compromisos": compromisos,
            "busqueda": busqueda,
            "estado": estado,
            "situacion": situacion,
            "resumen": resumen,
            "total_activos": Compromiso.objects.filter(
                activo=True
            ).count(),
            "total_inactivos": Compromiso.objects.filter(
                activo=False
            ).count(),
        },
    )


@login_required
@permission_required("tubo_gestionAPP.add_compromiso", raise_exception=True)
def compromiso_crear(request):
    if request.method == "POST":
        form = CompromisoForm(request.POST)

        if form.is_valid():
            compromiso = form.save()

            messages.success(
                request,
                "Compromiso registrado correctamente. "
                f"Estado calculado: {compromiso.get_estado_display()}.",
            )
            return redirect("compromiso_lista")
    else:
        form = CompromisoForm()

    return render(
        request,
        "tubo_gestion/compromiso_form.html",
        {
            "form": form,
            "titulo": "Registrar compromiso",
            "es_edicion": False,
        },
    )


@login_required
@permission_required("tubo_gestionAPP.change_compromiso", raise_exception=True)
def compromiso_editar(request, pk):
    compromiso = get_object_or_404(
        Compromiso.objects.select_related("delegacion"),
        pk=pk,
    )

    if request.method == "POST":
        form = CompromisoForm(request.POST, instance=compromiso)

        if form.is_valid():
            compromiso = form.save()

            messages.success(
                request,
                "Compromiso actualizado correctamente. "
                f"Estado calculado: {compromiso.get_estado_display()}.",
            )
            return redirect("compromiso_lista")
    else:
        form = CompromisoForm(instance=compromiso)

    return render(
        request,
        "tubo_gestion/compromiso_form.html",
        {
            "form": form,
            "compromiso": compromiso,
            "titulo": f"Editar compromiso: {compromiso.tarea}",
            "es_edicion": True,
        },
    )


@login_required
@permission_required("tubo_gestionAPP.delete_compromiso", raise_exception=True)
@require_POST
def compromiso_cambiar_estado(request, pk):
    compromiso = get_object_or_404(Compromiso, pk=pk)

    compromiso.activo = not compromiso.activo
    compromiso.save(update_fields=["activo"])

    if compromiso.activo:
        messages.success(
            request,
            "Compromiso reactivado correctamente.",
        )
    else:
        messages.success(
            request,
            "Compromiso dado de baja. Puede reactivarlo cuando sea "
            "necesario.",
        )

    return redirect("compromiso_lista")


# Alias histórico: los paneles y el menú usan "tablero_metas".
tablero_metas = compromiso_lista


# ============================================================
# PORTADA DEL MÓDULO
# ============================================================

@login_required
@permission_required("tubo_gestionAPP.view_compromiso", raise_exception=True)
def inicio(request):
    resumen = {"verde": 0, "amarillo": 0, "rojo": 0}

    for fila in Compromiso.objects.filter(activo=True).values(
        "estado"
    ).annotate(total=Count("pk")):
        if fila["estado"] in resumen:
            resumen[fila["estado"]] = fila["total"]

    return render(
        request,
        "tubo_gestion/inicio.html",
        {
            "resumen": resumen,
            "total": sum(resumen.values()),
        },
    )
