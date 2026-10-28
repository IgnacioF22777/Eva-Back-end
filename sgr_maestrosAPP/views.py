
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.db import IntegrityError
from django.db.models import Q
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
    busqueda = request.GET.get("q", "").strip()
    estado = request.GET.get("estado", "activos")

    actividades = CatalogoActividad.objects.all()

    if busqueda:
        actividades = actividades.filter(
            Q(codigo__icontains=busqueda)
            | Q(nombre__icontains=busqueda)
            | Q(area__icontains=busqueda)
            | Q(descripcion__icontains=busqueda)
        )

    if estado == "activos":
        actividades = actividades.filter(activo=True)
    elif estado == "inactivos":
        actividades = actividades.filter(activo=False)

    return render(
        request,
        "sgr_maestros/catalogo_lista.html",
        {
            "actividades": actividades,
            "busqueda": busqueda,
            "estado": estado,
            "total_activas": CatalogoActividad.objects.filter(
                activo=True
            ).count(),
            "total_inactivas": CatalogoActividad.objects.filter(
                activo=False
            ).count(),
        }
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
    busqueda = request.GET.get("q", "").strip()
    estado = request.GET.get("estado", "activos")

    detalles = DetallePeriodo.objects.select_related(
        "periodo"
    ).all()

    if busqueda:
        detalles = detalles.filter(
            Q(nombre__icontains=busqueda)
            | Q(periodo__codigo__icontains=busqueda)
            | Q(periodo__nombre__icontains=busqueda)
        )

    if estado == "activos":
        detalles = detalles.filter(activo=True)
    elif estado == "inactivos":
        detalles = detalles.filter(activo=False)

    return render(
        request,
        "sgr_maestros/detalle_periodo_lista.html",
        {
            "detalles": detalles,
            "busqueda": busqueda,
            "estado": estado,
            "total_activos": DetallePeriodo.objects.filter(
                activo=True
            ).count(),
            "total_inactivos": DetallePeriodo.objects.filter(
                activo=False
            ).count(),
        }
    )


@login_required
@permission_required("sgr_maestrosAPP.add_detalleperiodo", raise_exception=True)
def detalle_periodo_crear(request):
    # Si ya existe un detalle inactivo con el mismo nombre en el período,
    # se reactiva ese registro en lugar de crear un duplicado. Se usa como
    # instancia del formulario para que la validación de unicidad no lo
    # rechace a sí mismo.
    inactivo = None

    if request.method == "POST":
        nombre = (request.POST.get("nombre") or "").strip()
        periodo_id = request.POST.get("periodo")

        if nombre and periodo_id:
            inactivo = DetallePeriodo.objects.filter(
                periodo_id=periodo_id,
                nombre__iexact=nombre,
                activo=False,
            ).first()

        form = DetallePeriodoForm(request.POST, instance=inactivo)

        if form.is_valid():
            detalle = form.save(commit=False)
            detalle.activo = True

            try:
                detalle.save()
            except IntegrityError:
                form.add_error(
                    "nombre",
                    "Ya existe un detalle con este nombre en el "
                    "período seleccionado."
                )
            else:
                if inactivo:
                    messages.success(
                        request,
                        "Se reactivó el detalle existente en lugar de "
                        "duplicarlo."
                    )
                else:
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
            "No se puede cambiar el estado de detalles de períodos "
            "cerrados."
        )
        return redirect(
            "sgr_maestros:detalle_periodo_lista"
        )

    # Baja lógica: el detalle se conserva para no perder trazabilidad.
    detalle.activo = not detalle.activo
    detalle.save(update_fields=["activo"])

    if detalle.activo:
        messages.success(
            request,
            "Detalle de período reactivado correctamente."
        )
    else:
        messages.success(
            request,
            "Detalle de período dado de baja. Puede reactivarlo cuando "
            "sea necesario."
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
    busqueda = request.GET.get("q", "").strip()
    estado = request.GET.get("estado", "activos")

    metas = Meta.objects.select_related(
        "periodo",
        "actividad"
    ).all()

    if busqueda:
        metas = metas.filter(
            Q(codigo__icontains=busqueda)
            | Q(nombre__icontains=busqueda)
            | Q(periodo__codigo__icontains=busqueda)
            | Q(actividad__nombre__icontains=busqueda)
        )

    if estado == "activos":
        metas = metas.filter(activo=True)
    elif estado == "inactivos":
        metas = metas.filter(activo=False)

    return render(
        request,
        "sgr_maestros/meta_lista.html",
        {
            "metas": metas,
            "busqueda": busqueda,
            "estado": estado,
            "total_activas": Meta.objects.filter(activo=True).count(),
            "total_inactivas": Meta.objects.filter(activo=False).count(),
        }
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
