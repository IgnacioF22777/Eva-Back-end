from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from emergenciasTerritorialesAPP.ambito import filtrar_por_ambito, verificar_ambito

from .forms import DerivacionForm, ReporteCiudadanoForm
from .models import DerivacionReporte, ReporteCiudadano
from .transaccion import (
    ReglaNegocioError,
    anular_derivacion,
    derivar_reporte,
    modificar_derivacion,
    resolver_reporte,
)


def obtener_reporte(request, pk):
    """Busca el reporte (404) y verifica que sea de su delegación (403)."""
    reporte = get_object_or_404(
        ReporteCiudadano.objects.select_related("delegacion", "zona", "contacto"),
        pk=pk,
    )
    verificar_ambito(request.user, reporte.delegacion_id)
    return reporte


# ============================================================
# REPORTES CIUDADANOS: REGISTRO, CONSULTA, EDICIÓN Y BAJA
# ============================================================

def filtrar_reportes(request):
    busqueda = request.GET.get("q", "").strip()
    estado = request.GET.get("estado", "activos")
    situacion = request.GET.get("situacion", "")
    tipo = request.GET.get("tipo", "")

    reportes = filtrar_por_ambito(
        request.user,
        ReporteCiudadano.objects.select_related("delegacion", "zona", "contacto"),
    )

    if busqueda:
        reportes = reportes.filter(
            Q(descripcion__icontains=busqueda)
            | Q(ubicacion__icontains=busqueda)
            | Q(delegacion__nombre__icontains=busqueda)
            | Q(zona__nombre__icontains=busqueda)
        )

    if situacion in dict(ReporteCiudadano.ESTADO):
        reportes = reportes.filter(estado=situacion)
    else:
        situacion = ""

    if tipo in dict(ReporteCiudadano.TIPO_REPORTE):
        reportes = reportes.filter(tipo=tipo)
    else:
        tipo = ""

    if estado == "inactivos":
        reportes = reportes.filter(activo=False)
    elif estado != "todos":
        estado = "activos"
        reportes = reportes.filter(activo=True)

    return reportes, busqueda, estado, situacion, tipo


@login_required
@permission_required("reportesCiudadanosAPP.view_reporteciudadano", raise_exception=True)
def reporte_lista(request):
    reportes, busqueda, estado, situacion, tipo = filtrar_reportes(request)
    visibles = filtrar_por_ambito(
        request.user, ReporteCiudadano.objects.filter(activo=True)
    )

    return render(
        request,
        "reportes/reporte_lista.html",
        {
            "reportes": reportes,
            "busqueda": busqueda,
            "estado": estado,
            "situacion": situacion,
            "tipo": tipo,
            "situaciones": ReporteCiudadano.ESTADO,
            "tipos": ReporteCiudadano.TIPO_REPORTE,
            "total_pendientes": visibles.filter(estado="pendiente").count(),
            "total_derivados": visibles.filter(estado="derivado").count(),
            "total_resueltos": visibles.filter(estado="resuelto").count(),
        },
    )


@login_required
@permission_required("reportesCiudadanosAPP.add_reporteciudadano", raise_exception=True)
def reporte_crear(request):
    form = ReporteCiudadanoForm(request.POST or None, usuario=request.user)

    if request.method == "POST" and form.is_valid():
        verificar_ambito(request.user, form.cleaned_data["delegacion"].pk)
        reporte = form.save()
        messages.success(
            request,
            f"Reporte N.° {reporte.pk} registrado como pendiente.",
        )
        return redirect("reportes:reporte_detalle", pk=reporte.pk)

    return render(
        request,
        "emergencias/formulario.html",
        {
            "form": form,
            "titulo": "Registrar reporte ciudadano",
            "volver": "reportes:reporte_lista",
        },
    )


@login_required
@permission_required("reportesCiudadanosAPP.change_reporteciudadano", raise_exception=True)
def reporte_editar(request, pk):
    reporte = obtener_reporte(request, pk)

    if reporte.esta_resuelto:
        messages.error(request, "El reporte ya está resuelto: no se puede modificar.")
        return redirect("reportes:reporte_detalle", pk=reporte.pk)

    form = ReporteCiudadanoForm(
        request.POST or None, instance=reporte, usuario=request.user
    )

    if request.method == "POST" and form.is_valid():
        verificar_ambito(request.user, form.cleaned_data["delegacion"].pk)
        form.save()
        messages.success(request, "Reporte actualizado correctamente.")
        return redirect("reportes:reporte_detalle", pk=reporte.pk)

    return render(
        request,
        "emergencias/formulario.html",
        {
            "form": form,
            "titulo": f"Editar reporte N.° {reporte.pk}",
            "volver": "reportes:reporte_lista",
        },
    )


@login_required
@permission_required("reportesCiudadanosAPP.delete_reporteciudadano", raise_exception=True)
@require_POST
def reporte_cambiar_estado(request, pk):
    reporte = obtener_reporte(request, pk)

    if reporte.activo:
        if reporte.estado == "derivado":
            messages.error(
                request,
                "No se puede dar de baja un reporte derivado en curso. "
                "Anule la derivación o resuelva el reporte primero.",
            )
        else:
            reporte.activo = False
            reporte.save(update_fields=["activo"])
            messages.success(
                request,
                "Reporte dado de baja. Puede reactivarlo cuando sea necesario.",
            )
    elif not reporte.delegacion.activo:
        messages.error(request, "No se puede reactivar: la delegación está dada de baja.")
    else:
        reporte.activo = True
        reporte.save(update_fields=["activo"])
        messages.success(request, "Reporte reactivado correctamente.")

    return redirect("reportes:reporte_lista")


@login_required
@permission_required("reportesCiudadanosAPP.view_reporteciudadano", raise_exception=True)
def reporte_detalle(request, pk):
    reporte = obtener_reporte(request, pk)

    return render(
        request,
        "reportes/reporte_detalle.html",
        {
            "reporte": reporte,
            "derivaciones": reporte.derivaciones.select_related(
                "zona", "contacto", "usuario"
            ),
            "vigente": reporte.derivaciones.filter(activo=True).first(),
        },
    )


# ============================================================
# TRANSACCIÓN: DERIVACIÓN DEL REPORTE
# ============================================================

def _ejecutar(request, reporte, operacion, mensaje_ok):
    """Ejecuta una operación de la transacción y comunica el resultado."""
    try:
        operacion()
    except ReglaNegocioError as error:
        messages.error(request, str(error))
        return False

    messages.success(request, mensaje_ok)
    return True


@login_required
@permission_required("reportesCiudadanosAPP.add_derivacionreporte", raise_exception=True)
def reporte_derivar(request, pk):
    reporte = obtener_reporte(request, pk)
    form = DerivacionForm(request.POST or None, reporte=reporte)

    if request.method == "POST" and form.is_valid():
        hecho = _ejecutar(
            request,
            reporte,
            lambda: derivar_reporte(
                request.user,
                reporte.pk,
                form.cleaned_data["zona"].pk,
                form.cleaned_data["contacto"].pk,
                form.cleaned_data["observacion"],
            ),
            "Reporte derivado correctamente.",
        )
        if hecho:
            return redirect("reportes:reporte_detalle", pk=reporte.pk)

    return render(
        request,
        "reportes/derivacion_form.html",
        {
            "form": form,
            "reporte": reporte,
            "titulo": f"Derivar reporte N.° {reporte.pk}",
        },
    )


@login_required
@permission_required(
    "reportesCiudadanosAPP.change_derivacionreporte", raise_exception=True
)
def derivacion_editar(request, pk):
    derivacion = get_object_or_404(DerivacionReporte, pk=pk)
    reporte = obtener_reporte(request, derivacion.reporte_id)

    form = DerivacionForm(
        request.POST or None,
        reporte=reporte,
        initial={
            "zona": derivacion.zona_id,
            "contacto": derivacion.contacto_id,
            "observacion": derivacion.observacion,
        },
    )

    if request.method == "POST" and form.is_valid():
        hecho = _ejecutar(
            request,
            reporte,
            lambda: modificar_derivacion(
                request.user,
                derivacion.pk,
                form.cleaned_data["zona"].pk,
                form.cleaned_data["contacto"].pk,
                form.cleaned_data["observacion"],
            ),
            "Derivación modificada correctamente.",
        )
        if hecho:
            return redirect("reportes:reporte_detalle", pk=reporte.pk)

    return render(
        request,
        "reportes/derivacion_form.html",
        {
            "form": form,
            "reporte": reporte,
            "titulo": f"Modificar derivación del reporte N.° {reporte.pk}",
        },
    )


@login_required
@permission_required(
    "reportesCiudadanosAPP.delete_derivacionreporte", raise_exception=True
)
@require_POST
def derivacion_anular(request, pk):
    derivacion = get_object_or_404(DerivacionReporte, pk=pk)
    reporte = obtener_reporte(request, derivacion.reporte_id)

    _ejecutar(
        request,
        reporte,
        lambda: anular_derivacion(request.user, derivacion.pk),
        "Derivación anulada: el reporte volvió a quedar pendiente.",
    )
    return redirect("reportes:reporte_detalle", pk=reporte.pk)


@login_required
@permission_required(
    "reportesCiudadanosAPP.change_derivacionreporte", raise_exception=True
)
@require_POST
def reporte_resolver(request, pk):
    reporte = obtener_reporte(request, pk)

    _ejecutar(
        request,
        reporte,
        lambda: resolver_reporte(request.user, reporte.pk),
        "Reporte marcado como resuelto.",
    )
    return redirect("reportes:reporte_detalle", pk=reporte.pk)
