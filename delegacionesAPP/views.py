from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.db import IntegrityError
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .forms import DelegacionForm, ServicioForm
from .models import Delegacion, Servicio


# ============================================================
# MANTENEDOR 1: DELEGACIONES
# ============================================================

@login_required
@permission_required("delegacionesAPP.view_delegacion", raise_exception=True)
def delegacion_lista(request):
    busqueda = request.GET.get("q", "").strip()
    estado = request.GET.get("estado", "activos")

    delegaciones = Delegacion.objects.annotate(
        total_servicios=Count(
            "servicios",
            filter=Q(servicios__activo=True),
            distinct=True,
        ),
        total_compromisos=Count(
            "compromisos",
            filter=Q(compromisos__activo=True),
            distinct=True,
        ),
    ).order_by("nombre")

    if busqueda:
        delegaciones = delegaciones.filter(
            Q(nombre__icontains=busqueda)
            | Q(encargado__icontains=busqueda)
            | Q(email__icontains=busqueda)
            | Q(direccion__icontains=busqueda)
        )

    if estado == "activos":
        delegaciones = delegaciones.filter(activo=True)
    elif estado == "inactivos":
        delegaciones = delegaciones.filter(activo=False)

    return render(
        request,
        "delegaciones/lista_delegaciones.html",
        {
            "delegaciones": delegaciones,
            "busqueda": busqueda,
            "estado": estado,
            "total_activas": Delegacion.objects.filter(activo=True).count(),
            "total_inactivas": Delegacion.objects.filter(activo=False).count(),
        },
    )


@login_required
@permission_required("delegacionesAPP.add_delegacion", raise_exception=True)
def delegacion_crear(request):
    if request.method == "POST":
        form = DelegacionForm(request.POST)

        if form.is_valid():
            nombre = form.cleaned_data["nombre"]

            # Si el nombre pertenece a una delegación inactiva, se
            # reactiva en lugar de crear un duplicado.
            inactiva = Delegacion.objects.filter(
                nombre__iexact=nombre,
                activo=False,
            ).first()

            if inactiva:
                for campo, valor in form.cleaned_data.items():
                    setattr(inactiva, campo, valor)

                inactiva.activo = True
                inactiva.save()

                messages.success(
                    request,
                    "Se reactivó la delegación existente "
                    f"'{inactiva.nombre}' en lugar de duplicarla.",
                )
            else:
                delegacion = form.save()

                messages.success(
                    request,
                    f"Delegación '{delegacion.nombre}' registrada "
                    "correctamente.",
                )

            return redirect("delegacion_lista")
    else:
        form = DelegacionForm()

    return render(
        request,
        "delegaciones/delegacion_form.html",
        {
            "form": form,
            "titulo": "Registrar delegación",
            "es_edicion": False,
        },
    )


@login_required
@permission_required("delegacionesAPP.change_delegacion", raise_exception=True)
def delegacion_editar(request, pk):
    delegacion = get_object_or_404(Delegacion, pk=pk)

    if request.method == "POST":
        form = DelegacionForm(request.POST, instance=delegacion)

        if form.is_valid():
            form.save()

            messages.success(
                request,
                "Delegación actualizada correctamente.",
            )
            return redirect("delegacion_lista")
    else:
        form = DelegacionForm(instance=delegacion)

    return render(
        request,
        "delegaciones/delegacion_form.html",
        {
            "form": form,
            "titulo": f"Editar delegación: {delegacion.nombre}",
            "delegacion": delegacion,
            "es_edicion": True,
        },
    )


@login_required
@permission_required("delegacionesAPP.delete_delegacion", raise_exception=True)
@require_POST
def delegacion_cambiar_estado(request, pk):
    delegacion = get_object_or_404(Delegacion, pk=pk)

    if delegacion.activo:
        if not delegacion.puede_dar_de_baja():
            messages.error(
                request,
                "No se puede dar de baja la delegación porque tiene "
                "servicios o compromisos activos. Desactívelos primero.",
            )
        else:
            delegacion.activo = False
            delegacion.save(update_fields=["activo"])

            messages.success(
                request,
                "Delegación dada de baja. Puede reactivarla cuando "
                "sea necesario.",
            )
    else:
        duplicada = Delegacion.objects.filter(
            nombre__iexact=delegacion.nombre,
            activo=True,
        ).exclude(pk=delegacion.pk).exists()

        if duplicada:
            messages.error(
                request,
                "No se puede reactivar: ya existe otra delegación "
                "activa con el mismo nombre.",
            )
        else:
            delegacion.activo = True
            delegacion.save(update_fields=["activo"])

            messages.success(
                request,
                "Delegación reactivada correctamente.",
            )

    return redirect("delegacion_lista")


# ============================================================
# MANTENEDOR 2: SERVICIOS (ANIDADO EN LA DELEGACIÓN)
# ============================================================

@login_required
@permission_required("delegacionesAPP.view_delegacion", raise_exception=True)
def delegacion_detalle(request, pk):
    delegacion = get_object_or_404(Delegacion, pk=pk)

    busqueda = request.GET.get("q", "").strip()
    estado = request.GET.get("estado", "activos")

    servicios = delegacion.servicios.all()

    if busqueda:
        servicios = servicios.filter(nombre__icontains=busqueda)

    if estado == "activos":
        servicios = servicios.filter(activo=True)
    elif estado == "inactivos":
        servicios = servicios.filter(activo=False)

    return render(
        request,
        "delegaciones/delegacion_detalle.html",
        {
            "delegacion": delegacion,
            "servicios": servicios,
            "busqueda": busqueda,
            "estado": estado,
            "total_activos": delegacion.servicios.filter(activo=True).count(),
            "total_inactivos": delegacion.servicios.filter(
                activo=False
            ).count(),
        },
    )


@login_required
@permission_required("delegacionesAPP.add_servicio", raise_exception=True)
def servicio_crear(request, delegacion_pk):
    delegacion = get_object_or_404(Delegacion, pk=delegacion_pk)

    if not delegacion.activo:
        messages.error(
            request,
            "No se pueden agregar servicios a una delegación dada de baja.",
        )
        return redirect("delegacion_detalle", pk=delegacion.pk)

    if request.method == "POST":
        form = ServicioForm(request.POST, delegacion=delegacion)

        if form.is_valid():
            nombre = form.cleaned_data["nombre"]

            existente = Servicio.objects.filter(
                delegacion=delegacion,
                nombre__iexact=nombre,
            ).first()

            if existente and existente.activo:
                form.add_error(
                    "nombre",
                    "Ya existe un servicio activo con este nombre.",
                )
            elif existente:
                existente.nombre = nombre
                existente.activo = True
                existente.save()

                messages.success(
                    request,
                    "Se reactivó el servicio existente "
                    f"'{existente.nombre}' en lugar de duplicarlo.",
                )
                return redirect("delegacion_detalle", pk=delegacion.pk)
            else:
                try:
                    servicio = form.save(commit=False)
                    servicio.delegacion = delegacion
                    servicio.save()

                    messages.success(
                        request,
                        "Servicio registrado correctamente.",
                    )
                    return redirect("delegacion_detalle", pk=delegacion.pk)
                except IntegrityError:
                    form.add_error(
                        "nombre",
                        "Ya existe un servicio con este nombre en la "
                        "delegación.",
                    )
    else:
        form = ServicioForm(delegacion=delegacion)

    return render(
        request,
        "delegaciones/servicio_form.html",
        {
            "form": form,
            "delegacion": delegacion,
            "titulo": "Registrar servicio",
            "es_edicion": False,
        },
    )


@login_required
@permission_required("delegacionesAPP.change_servicio", raise_exception=True)
def servicio_editar(request, pk):
    servicio = get_object_or_404(
        Servicio.objects.select_related("delegacion"),
        pk=pk,
    )
    delegacion = servicio.delegacion

    if request.method == "POST":
        form = ServicioForm(
            request.POST,
            instance=servicio,
            delegacion=delegacion,
        )

        if form.is_valid():
            try:
                form.save()

                messages.success(
                    request,
                    "Servicio actualizado correctamente.",
                )
                return redirect("delegacion_detalle", pk=delegacion.pk)
            except IntegrityError:
                form.add_error(
                    "nombre",
                    "Ya existe un servicio con este nombre en la "
                    "delegación.",
                )
    else:
        form = ServicioForm(instance=servicio, delegacion=delegacion)

    return render(
        request,
        "delegaciones/servicio_form.html",
        {
            "form": form,
            "delegacion": delegacion,
            "servicio": servicio,
            "titulo": f"Editar servicio: {servicio.nombre}",
            "es_edicion": True,
        },
    )


@login_required
@permission_required("delegacionesAPP.delete_servicio", raise_exception=True)
@require_POST
def servicio_cambiar_estado(request, pk):
    servicio = get_object_or_404(
        Servicio.objects.select_related("delegacion"),
        pk=pk,
    )

    if servicio.activo:
        # Un servicio con compromisos activos no puede darse de baja:
        # primero hay que reasignarlos o desactivarlos. La comprobación
        # se hace en el servidor para que no dependa del formulario.
        if servicio.compromisos.filter(activo=True).exists():
            messages.error(
                request,
                "No se puede dar de baja el servicio porque tiene "
                "compromisos activos asignados. Reasígnelos o "
                "desactívelos primero.",
            )
            return redirect("delegacion_detalle", pk=servicio.delegacion_id)

        servicio.activo = False
        servicio.save(update_fields=["activo"])

        messages.success(
            request,
            "Servicio dado de baja. Puede reactivarlo cuando sea necesario.",
        )
    else:
        if not servicio.delegacion.activo:
            messages.error(
                request,
                "No se puede reactivar el servicio porque su delegación "
                "está dada de baja.",
            )
        else:
            servicio.activo = True
            servicio.save(update_fields=["activo"])

            messages.success(
                request,
                "Servicio reactivado correctamente.",
            )

    return redirect("delegacion_detalle", pk=servicio.delegacion_id)


# ============================================================
# PORTADA PÚBLICA
# ============================================================

@login_required
def inicio(request):
    data = Delegacion.objects.filter(activo=True)

    return render(
        request,
        "delegaciones/inicio.html",
        {"delegaciones": data},
    )
