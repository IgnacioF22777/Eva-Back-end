from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .ambito import filtrar_por_ambito, verificar_ambito
from .forms import ContactoEmergenciaForm, ZonaRiesgoForm
from .models import ContactoEmergencia, ZonaRiesgo


# ============================================================
# UTILIDADES COMPARTIDAS
# ============================================================

def filtrar_estado(queryset, estado):
    if estado == "inactivos":
        return queryset.filter(activo=False)
    if estado == "todos":
        return queryset
    return queryset.filter(activo=True)


def obtener_en_ambito(request, modelo, pk):
    """Busca el registro (404) y verifica que sea de su delegación (403)."""
    registro = get_object_or_404(modelo, pk=pk)
    verificar_ambito(request.user, registro.delegacion_id)
    return registro


# ============================================================
# MANTENEDOR 1: ZONAS DE RIESGO
# ============================================================

def filtrar_zonas(request):
    busqueda = request.GET.get("q", "").strip()
    estado = request.GET.get("estado", "activos")
    nivel = request.GET.get("nivel", "")

    zonas = filtrar_por_ambito(
        request.user,
        ZonaRiesgo.objects.select_related("delegacion").annotate(
            total_contactos=Count(
                "contactos", filter=Q(contactos__activo=True), distinct=True
            ),
            total_reportes=Count(
                "reportes", filter=Q(reportes__activo=True), distinct=True
            ),
        ),
    )

    if busqueda:
        zonas = zonas.filter(
            Q(nombre__icontains=busqueda)
            | Q(descripcion_riesgo__icontains=busqueda)
            | Q(delegacion__nombre__icontains=busqueda)
        )

    if nivel in dict(ZonaRiesgo.NIVELES_PELIGRO):
        zonas = zonas.filter(nivel_peligro=nivel)
    else:
        nivel = ""

    return filtrar_estado(zonas, estado), busqueda, estado, nivel


@login_required
@permission_required("emergenciasTerritorialesAPP.view_zonariesgo", raise_exception=True)
def zona_lista(request):
    zonas, busqueda, estado, nivel = filtrar_zonas(request)
    visibles = filtrar_por_ambito(request.user, ZonaRiesgo.objects.all())

    return render(
        request,
        "emergencias/zona_lista.html",
        {
            "zonas": zonas,
            "busqueda": busqueda,
            "estado": estado,
            "nivel": nivel,
            "niveles": ZonaRiesgo.NIVELES_PELIGRO,
            "total_activas": visibles.filter(activo=True).count(),
            "total_inactivas": visibles.filter(activo=False).count(),
        },
    )


@login_required
@permission_required("emergenciasTerritorialesAPP.add_zonariesgo", raise_exception=True)
def zona_crear(request):
    form = ZonaRiesgoForm(request.POST or None, usuario=request.user)

    if request.method == "POST" and form.is_valid():
        verificar_ambito(request.user, form.cleaned_data["delegacion"].pk)
        zona = form.save()
        messages.success(request, f"Zona '{zona.nombre}' registrada correctamente.")
        return redirect("emergencias:zona_lista")

    return render(
        request,
        "emergencias/formulario.html",
        {
            "form": form,
            "titulo": "Registrar zona de riesgo",
            "volver": "emergencias:zona_lista",
        },
    )


@login_required
@permission_required("emergenciasTerritorialesAPP.change_zonariesgo", raise_exception=True)
def zona_editar(request, pk):
    zona = obtener_en_ambito(request, ZonaRiesgo, pk)
    form = ZonaRiesgoForm(request.POST or None, instance=zona, usuario=request.user)

    if request.method == "POST" and form.is_valid():
        verificar_ambito(request.user, form.cleaned_data["delegacion"].pk)
        form.save()
        messages.success(request, "Zona de riesgo actualizada correctamente.")
        return redirect("emergencias:zona_lista")

    return render(
        request,
        "emergencias/formulario.html",
        {
            "form": form,
            "titulo": f"Editar zona: {zona.nombre}",
            "volver": "emergencias:zona_lista",
        },
    )


@login_required
@permission_required("emergenciasTerritorialesAPP.delete_zonariesgo", raise_exception=True)
@require_POST
def zona_cambiar_estado(request, pk):
    zona = obtener_en_ambito(request, ZonaRiesgo, pk)

    if zona.activo:
        if not zona.puede_dar_de_baja():
            messages.error(
                request,
                "No se puede dar de baja la zona: tiene contactos asignados "
                "o reportes en curso. Reasígnelos o resuélvalos primero.",
            )
        else:
            zona.activo = False
            zona.save(update_fields=["activo"])
            messages.success(
                request,
                "Zona dada de baja. Puede reactivarla cuando sea necesario.",
            )
    else:
        duplicada = ZonaRiesgo.objects.filter(
            nombre__iexact=zona.nombre,
            delegacion_id=zona.delegacion_id,
            activo=True,
        ).exclude(pk=zona.pk).exists()

        if duplicada:
            messages.error(
                request,
                "No se puede reactivar: ya existe otra zona activa con el "
                "mismo nombre en la delegación.",
            )
        elif not zona.delegacion.activo:
            messages.error(
                request,
                "No se puede reactivar: la delegación está dada de baja.",
            )
        else:
            zona.activo = True
            zona.save(update_fields=["activo"])
            messages.success(request, "Zona reactivada correctamente.")

    return redirect("emergencias:zona_lista")


# ============================================================
# MANTENEDOR 2: CONTACTOS DE EMERGENCIA
# ============================================================

def filtrar_contactos(request):
    busqueda = request.GET.get("q", "").strip()
    estado = request.GET.get("estado", "activos")

    contactos = filtrar_por_ambito(
        request.user,
        ContactoEmergencia.objects.select_related("delegacion", "zona_asignada"),
    )

    if busqueda:
        contactos = contactos.filter(
            Q(nombre__icontains=busqueda)
            | Q(cargo__icontains=busqueda)
            | Q(delegacion__nombre__icontains=busqueda)
            | Q(zona_asignada__nombre__icontains=busqueda)
        )

    return filtrar_estado(contactos, estado), busqueda, estado


@login_required
@permission_required(
    "emergenciasTerritorialesAPP.view_contactoemergencia", raise_exception=True
)
def contacto_lista(request):
    contactos, busqueda, estado = filtrar_contactos(request)
    visibles = filtrar_por_ambito(request.user, ContactoEmergencia.objects.all())

    return render(
        request,
        "emergencias/contacto_lista.html",
        {
            "contactos": contactos,
            "busqueda": busqueda,
            "estado": estado,
            "total_activos": visibles.filter(activo=True).count(),
            "total_inactivos": visibles.filter(activo=False).count(),
        },
    )


@login_required
@permission_required(
    "emergenciasTerritorialesAPP.add_contactoemergencia", raise_exception=True
)
def contacto_crear(request):
    form = ContactoEmergenciaForm(request.POST or None, usuario=request.user)

    if request.method == "POST" and form.is_valid():
        verificar_ambito(request.user, form.cleaned_data["delegacion"].pk)
        contacto = form.save()
        messages.success(
            request, f"Contacto '{contacto.nombre}' registrado correctamente."
        )
        return redirect("emergencias:contacto_lista")

    return render(
        request,
        "emergencias/formulario.html",
        {
            "form": form,
            "titulo": "Registrar contacto de emergencia",
            "volver": "emergencias:contacto_lista",
        },
    )


@login_required
@permission_required(
    "emergenciasTerritorialesAPP.change_contactoemergencia", raise_exception=True
)
def contacto_editar(request, pk):
    contacto = obtener_en_ambito(request, ContactoEmergencia, pk)
    form = ContactoEmergenciaForm(
        request.POST or None, instance=contacto, usuario=request.user
    )

    if request.method == "POST" and form.is_valid():
        verificar_ambito(request.user, form.cleaned_data["delegacion"].pk)
        form.save()
        messages.success(request, "Contacto actualizado correctamente.")
        return redirect("emergencias:contacto_lista")

    return render(
        request,
        "emergencias/formulario.html",
        {
            "form": form,
            "titulo": f"Editar contacto: {contacto.nombre}",
            "volver": "emergencias:contacto_lista",
        },
    )


@login_required
@permission_required(
    "emergenciasTerritorialesAPP.delete_contactoemergencia", raise_exception=True
)
@require_POST
def contacto_cambiar_estado(request, pk):
    contacto = obtener_en_ambito(request, ContactoEmergencia, pk)

    if contacto.activo:
        if not contacto.puede_dar_de_baja():
            messages.error(
                request,
                "No se puede dar de baja el contacto: tiene reportes "
                "derivados en curso. Rederívelos o resuélvalos primero.",
            )
        else:
            contacto.activo = False
            contacto.save(update_fields=["activo"])
            messages.success(
                request,
                "Contacto dado de baja. Puede reactivarlo cuando sea necesario.",
            )
    elif not contacto.delegacion.activo:
        messages.error(
            request, "No se puede reactivar: la delegación está dada de baja."
        )
    else:
        contacto.activo = True
        contacto.save(update_fields=["activo"])
        messages.success(request, "Contacto reactivado correctamente.")

    return redirect("emergencias:contacto_lista")
