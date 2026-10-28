
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.views.decorators.http import require_POST

from .models import (
    CatalogoActividad,
    Periodo,
    DetallePeriodo,
    Meta,
)

from .forms import (
    CatalogoActividadForm,
    PeriodoForm,
    DetallePeriodoForm,
    MetaForm,
)


# ============================================================
# CRUD 1: CATÁLOGO DE ACTIVIDADES
# ============================================================

@login_required
@permission_required("sgr_maestrosAPP.view_catalogoactividad", raise_exception=True)
def catalogo_lista(request):
    actividades = CatalogoActividad.objects.all()

    return render(
        request,
        "sgr_maestros/catalogo_lista.html",
        {"actividades": actividades}
    )


@login_required
@permission_required("sgr_maestrosAPP.add_catalogoactividad", raise_exception=True)
def catalogo_crear(request):
    if request.method == "POST":
        form = CatalogoActividadForm(request.POST)

        if form.is_valid():
            form.save()
            messages.success(
                request,
                "Actividad registrada correctamente."
            )
            return redirect("sgr_maestros:catalogo_lista")
    else:
        form = CatalogoActividadForm()

    return render(
        request,
        "sgr_maestros/catalogo_form.html",
        {
            "form": form,
            "titulo": "Registrar actividad",
        }
    )


@login_required
@permission_required("sgr_maestrosAPP.change_catalogoactividad", raise_exception=True)
def catalogo_editar(request, pk):
    actividad = get_object_or_404(
        CatalogoActividad,
        pk=pk
    )

    if request.method == "POST":
        form = CatalogoActividadForm(
            request.POST,
            instance=actividad
        )

        if form.is_valid():
            form.save()
            messages.success(
                request,
                "Actividad actualizada correctamente."
            )
            return redirect("sgr_maestros:catalogo_lista")
    else:
        form = CatalogoActividadForm(instance=actividad)

    return render(
        request,
        "sgr_maestros/catalogo_form.html",
        {
            "form": form,
            "titulo": "Editar actividad",
        }
    )


@login_required
@permission_required("sgr_maestrosAPP.change_catalogoactividad", raise_exception=True)
@require_POST
def catalogo_cambiar_estado(request, pk):
    actividad = get_object_or_404(
        CatalogoActividad,
        pk=pk
    )

    actividad.activo = not actividad.activo
    actividad.save(update_fields=["activo"])

    messages.success(
        request,
        "Estado de la actividad actualizado correctamente."
    )

    return redirect("sgr_maestros:catalogo_lista")


# ============================================================
# CRUD 2: GESTIÓN DE PERÍODOS
# ============================================================

@login_required
@permission_required("sgr_maestrosAPP.view_periodo", raise_exception=True)
def periodo_lista(request):
    periodos = Periodo.objects.all()

    return render(
        request,
        "sgr_maestros/periodo_lista.html",
        {"periodos": periodos}
    )


@login_required
@permission_required("sgr_maestrosAPP.add_periodo", raise_exception=True)
def periodo_crear(request):
    if request.method == "POST":
        form = PeriodoForm(request.POST)

        if form.is_valid():
            form.save()
            messages.success(
                request,
                "Período registrado correctamente."
            )
            return redirect("sgr_maestros:periodo_lista")
    else:
        form = PeriodoForm()

    return render(
        request,
        "sgr_maestros/periodo_form.html",
        {
            "form": form,
            "titulo": "Registrar período",
        }
    )


@login_required
@permission_required("sgr_maestrosAPP.change_periodo", raise_exception=True)
def periodo_editar(request, pk):
    periodo = get_object_or_404(Periodo, pk=pk)

    if periodo.cerrado:
        messages.error(
            request,
            "Este período está cerrado y no puede modificarse."
        )
        return redirect("sgr_maestros:periodo_lista")

    if request.method == "POST":
        form = PeriodoForm(
            request.POST,
            instance=periodo
        )

        if form.is_valid():
            form.save()
            messages.success(
                request,
                "Período actualizado correctamente."
            )
            return redirect("sgr_maestros:periodo_lista")
    else:
        form = PeriodoForm(instance=periodo)

    return render(
        request,
        "sgr_maestros/periodo_form.html",
        {
            "form": form,
            "titulo": "Editar período",
        }
    )


# ============================================================
# CRUD 3: DETALLE DE PERÍODO
# ============================================================

@login_required
@permission_required("sgr_maestrosAPP.view_detalleperiodo", raise_exception=True)
def detalle_periodo_lista(request):
    detalles = DetallePeriodo.objects.select_related(
        "periodo"
    ).all()

    return render(
        request,
        "sgr_maestros/detalle_periodo_lista.html",
        {"detalles": detalles}
    )


@login_required
@permission_required("sgr_maestrosAPP.add_detalleperiodo", raise_exception=True)
def detalle_periodo_crear(request):
    if request.method == "POST":
        form = DetallePeriodoForm(request.POST)

        if form.is_valid():
            form.save()
            messages.success(
                request,
                "Detalle de período registrado correctamente."
            )
            return redirect(
                "sgr_maestros:detalle_periodo_lista"
            )
    else:
        form = DetallePeriodoForm()

    return render(
        request,
        "sgr_maestros/detalle_periodo_form.html",
        {
            "form": form,
            "titulo": "Registrar detalle de período",
        }
    )


@login_required
@permission_required("sgr_maestrosAPP.change_detalleperiodo", raise_exception=True)
def detalle_periodo_editar(request, pk):
    detalle = get_object_or_404(
        DetallePeriodo.objects.select_related("periodo"),
        pk=pk
    )

    if detalle.periodo.cerrado:
        messages.error(
            request,
            "No puedes modificar detalles de períodos cerrados."
        )
        return redirect(
            "sgr_maestros:detalle_periodo_lista"
        )

    if request.method == "POST":
        form = DetallePeriodoForm(
            request.POST,
            instance=detalle
        )

        if form.is_valid():
            form.save()
            messages.success(
                request,
                "Detalle de período actualizado correctamente."
            )
            return redirect(
                "sgr_maestros:detalle_periodo_lista"
            )
    else:
        form = DetallePeriodoForm(instance=detalle)

    return render(
        request,
        "sgr_maestros/detalle_periodo_form.html",
        {
            "form": form,
            "titulo": "Editar detalle de período",
        }
    )


@login_required
@permission_required("sgr_maestrosAPP.delete_detalleperiodo", raise_exception=True)
@require_POST
def detalle_periodo_eliminar(request, pk):
    detalle = get_object_or_404(
        DetallePeriodo.objects.select_related("periodo"),
        pk=pk
    )

    if detalle.periodo.cerrado:
        messages.error(
            request,
            "No puedes eliminar detalles de períodos cerrados."
        )
        return redirect(
            "sgr_maestros:detalle_periodo_lista"
        )

    detalle.delete()

    messages.success(
        request,
        "Detalle de período eliminado correctamente."
    )

    return redirect(
        "sgr_maestros:detalle_periodo_lista"
    )


# ============================================================
# CRUD 4: GESTIÓN DE METAS
# ============================================================

@login_required
@permission_required("sgr_maestrosAPP.view_meta", raise_exception=True)
def meta_lista(request):
    metas = Meta.objects.select_related(
        "periodo",
        "actividad"
    ).all()

    return render(
        request,
        "sgr_maestros/meta_lista.html",
        {"metas": metas}
    )


@login_required
@permission_required("sgr_maestrosAPP.add_meta", raise_exception=True)
def meta_crear(request):
    if request.method == "POST":
        form = MetaForm(request.POST)

        if form.is_valid():
            form.save()

            messages.success(
                request,
                "Meta registrada correctamente."
            )

            return redirect("sgr_maestros:meta_lista")
    else:
        form = MetaForm()

    return render(
        request,
        "sgr_maestros/meta_form.html",
        {
            "form": form,
            "titulo": "Registrar meta",
        }
    )


@login_required
@permission_required("sgr_maestrosAPP.change_meta", raise_exception=True)
def meta_editar(request, pk):
    meta = get_object_or_404(
        Meta.objects.select_related(
            "periodo",
            "actividad"
        ),
        pk=pk
    )

    if meta.periodo.cerrado:
        messages.error(
            request,
            "No puedes modificar una meta de un período cerrado."
        )

        return redirect("sgr_maestros:meta_lista")

    if request.method == "POST":
        form = MetaForm(
            request.POST,
            instance=meta
        )

        if form.is_valid():
            form.save()

            messages.success(
                request,
                "Meta actualizada correctamente."
            )

            return redirect("sgr_maestros:meta_lista")
    else:
        form = MetaForm(instance=meta)

    return render(
        request,
        "sgr_maestros/meta_form.html",
        {
            "form": form,
            "titulo": "Editar meta",
        }
    )


@login_required
@permission_required("sgr_maestrosAPP.change_meta", raise_exception=True)
@require_POST
def meta_cambiar_estado(request, pk):
    meta = get_object_or_404(
        Meta.objects.select_related(
            "periodo",
            "actividad"
        ),
        pk=pk
    )

    if meta.periodo.cerrado:
        messages.error(
            request,
            "No puedes modificar metas de períodos cerrados."
        )

        return redirect("sgr_maestros:meta_lista")

    if not meta.activo and not meta.actividad.activo:
        messages.error(
            request,
            "No puedes reactivar una meta asociada "
            "a una actividad inactiva."
        )

        return redirect("sgr_maestros:meta_lista")

    meta.activo = not meta.activo
    meta.save(update_fields=["activo"])

    messages.success(
        request,
        "Estado de la meta actualizado correctamente."
    )

    return redirect("sgr_maestros:meta_lista")
