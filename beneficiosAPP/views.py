from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from config import exportar
from tubo_gestionAPP.ambito import es_global

from .ambito import (
    ninos_visibles,
    verificar_administra_campanas,
    verificar_puede_inscribir,
    verificar_puede_modificar,
)
from .forms import CampanaRegaloForm, NinoInscritoForm
from .models import CampanaRegalo, NinoInscrito


# ============================================================
# NIÑOS INSCRITOS
# ============================================================

def filtrar_ninos(request):
    """Listado según el ámbito del usuario, con los filtros de la pantalla."""
    ninos = ninos_visibles(
        request.user,
        NinoInscrito.objects.select_related("campana", "delegacion", "registrado_por"),
    )

    campanas = CampanaRegalo.objects.all()
    campana_id = request.GET.get("campana", "")
    if not campana_id:
        primera = campanas.filter(activo=True).first() or campanas.first()
        campana_id = str(primera.pk) if primera else ""

    if campana_id.isdigit():
        ninos = ninos.filter(campana_id=int(campana_id))
    else:
        campana_id = ""

    busqueda = request.GET.get("q", "").strip()
    if busqueda:
        rut = busqueda.replace(".", "").upper()
        ninos = ninos.filter(
            Q(nombre__icontains=busqueda)
            | Q(apellido__icontains=busqueda)
            | Q(rut__icontains=rut)
        )

    sexo = request.GET.get("sexo", "")
    if sexo in dict(NinoInscrito.SEXOS):
        ninos = ninos.filter(sexo=sexo)
    else:
        sexo = ""

    estado = request.GET.get("estado", "vigentes")
    if estado == "vigentes":
        ninos = ninos.filter(activo=True)
    elif estado == "anulados":
        ninos = ninos.filter(activo=False)
    else:
        estado = "todos"

    filtros = {
        "campanas": campanas,
        "campana_id": campana_id,
        "busqueda": busqueda,
        "sexo": sexo,
        "sexos": NinoInscrito.SEXOS,
        "estado": estado,
    }
    return ninos, filtros


@login_required
@permission_required("beneficiosAPP.view_ninoinscrito", raise_exception=True)
def nino_lista(request):
    ninos, filtros = filtrar_ninos(request)
    resumen = ninos.filter(activo=True).aggregate(
        total=Count("id"),
        ninas=Count("id", filter=Q(sexo=NinoInscrito.FEMENINO)),
        ninos=Count("id", filter=Q(sexo=NinoInscrito.MASCULINO)),
    )

    return render(request, "beneficios/nino_lista.html", {
        "ninos": ninos,
        "resumen": resumen,
        "ve_todas": es_global(request.user),
        **filtros,
    })


def guardar_nino(request, form):
    """
    Guarda con la delegación y el usuario que inscribe. La campaña se
    bloquea mientras se revisa el RUT, para que dos delegaciones no
    inscriban al mismo niño al mismo tiempo.
    """
    nino = form.save(commit=False)

    with transaction.atomic():
        CampanaRegalo.objects.select_for_update().get(pk=nino.campana_id)

        if nino.pk is None:
            nino.delegacion_id = verificar_puede_inscribir(request.user)
            nino.registrado_por = request.user

        try:
            nino.full_clean()
        except ValidationError as error:
            for campo, mensajes in error.message_dict.items():
                form.add_error(campo if campo in form.fields else None, mensajes)
            return None

        nino.save()

    return nino


@login_required
@permission_required("beneficiosAPP.add_ninoinscrito", raise_exception=True)
def nino_crear(request):
    verificar_puede_inscribir(request.user)
    form = NinoInscritoForm(request.POST or None)

    if not form.fields["campana"].queryset.exists():
        messages.warning(
            request,
            "No hay campañas con inscripciones abiertas. El Administrador "
            "debe crear o abrir una campaña.",
        )
        return redirect("beneficios:nino_lista")

    if request.method == "POST" and form.is_valid():
        nino = guardar_nino(request, form)
        if nino:
            messages.success(request, f"{nino.nombre} {nino.apellido} quedó inscrito en {nino.campana}.")
            return redirect("beneficios:nino_lista")

    return render(request, "matriz/formulario.html", {
        "form": form,
        "titulo": "Inscribir niño",
        "ayuda": (
            "Un RUT se inscribe una sola vez por campaña en toda la comuna: "
            "si otra delegación ya lo inscribió, el sistema lo avisa."
        ),
        "volver": "beneficios:nino_lista",
    })


@login_required
@permission_required("beneficiosAPP.change_ninoinscrito", raise_exception=True)
def nino_editar(request, pk):
    nino = get_object_or_404(NinoInscrito.objects.select_related("campana"), pk=pk)
    verificar_puede_modificar(request.user, nino)

    form = NinoInscritoForm(request.POST or None, instance=nino)

    if request.method == "POST" and form.is_valid():
        if guardar_nino(request, form):
            messages.success(request, "Datos del niño actualizados.")
            return redirect("beneficios:nino_lista")

    return render(request, "matriz/formulario.html", {
        "form": form,
        "titulo": f"Corregir datos de {nino.nombre} {nino.apellido}",
        "volver": "beneficios:nino_lista",
    })


@login_required
@permission_required("beneficiosAPP.delete_ninoinscrito", raise_exception=True)
@require_POST
def nino_cambiar_estado(request, pk):
    nino = get_object_or_404(NinoInscrito.objects.select_related("campana"), pk=pk)
    verificar_puede_modificar(request.user, nino)

    nino.activo = not nino.activo

    if nino.activo:
        # Al reactivar, el RUT no puede estar inscrito de nuevo por otra delegación.
        with transaction.atomic():
            CampanaRegalo.objects.select_for_update().get(pk=nino.campana_id)
            try:
                nino.full_clean()
            except ValidationError as error:
                messages.error(request, "No se puede reactivar: " + " ".join(error.messages))
                return redirect("beneficios:nino_lista")
            nino.save(update_fields=["activo"])
    else:
        nino.save(update_fields=["activo"])

    messages.success(
        request,
        "Inscripción reactivada." if nino.activo
        else "Inscripción anulada: el RUT queda libre para esta campaña.",
    )
    return redirect("beneficios:nino_lista")


ENCABEZADOS_NINOS = [
    "Campaña", "RUT", "Nombre", "Apellido", "Sexo", "Fecha de nacimiento",
    "Edad", "Delegación", "Inscrito por", "Estado",
]


@login_required
@permission_required("beneficiosAPP.view_ninoinscrito", raise_exception=True)
def nino_exportar_excel(request):
    """Planilla para la compra y entrega de regalos (mismos filtros y ámbito)."""
    ninos, _ = filtrar_ninos(request)
    filas = [
        [
            str(nino.campana),
            nino.rut_formateado,
            nino.nombre,
            nino.apellido,
            nino.get_sexo_display(),
            nino.fecha_nacimiento,
            nino.edad,
            nino.delegacion.nombre if nino.delegacion else "",
            exportar.nombre_usuario(nino.registrado_por),
            "Vigente" if nino.activo else "Anulada",
        ]
        for nino in ninos
    ]
    return exportar.exportar_excel(
        "Niños inscritos para regalos", ENCABEZADOS_NINOS, filas,
        "ninos_inscritos", usuario=request.user,
    )


# ============================================================
# CAMPAÑAS (solo Administrador)
# ============================================================

@login_required
@permission_required("beneficiosAPP.add_campanaregalo", raise_exception=True)
def campana_lista(request):
    verificar_administra_campanas(request.user)
    campanas = CampanaRegalo.objects.annotate(
        total=Count("inscritos", filter=Q(inscritos__activo=True))
    )
    return render(request, "beneficios/campana_lista.html", {"campanas": campanas})


@login_required
@permission_required("beneficiosAPP.add_campanaregalo", raise_exception=True)
def campana_crear(request):
    verificar_administra_campanas(request.user)
    form = CampanaRegaloForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        campana = form.save()
        messages.success(request, f"Campaña {campana} creada.")
        return redirect("beneficios:campana_lista")

    return render(request, "matriz/formulario.html", {
        "form": form,
        "titulo": "Nueva campaña de regalos",
        "ayuda": "Las delegaciones podrán inscribir niños solo entre las fechas indicadas.",
        "volver": "beneficios:campana_lista",
    })


@login_required
@permission_required("beneficiosAPP.change_campanaregalo", raise_exception=True)
def campana_editar(request, pk):
    verificar_administra_campanas(request.user)
    campana = get_object_or_404(CampanaRegalo, pk=pk)
    form = CampanaRegaloForm(request.POST or None, instance=campana)

    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Campaña actualizada.")
        return redirect("beneficios:campana_lista")

    return render(request, "matriz/formulario.html", {
        "form": form,
        "titulo": f"Editar campaña {campana}",
        "volver": "beneficios:campana_lista",
    })


@login_required
@permission_required("beneficiosAPP.change_campanaregalo", raise_exception=True)
@require_POST
def campana_cambiar_estado(request, pk):
    verificar_administra_campanas(request.user)
    campana = get_object_or_404(CampanaRegalo, pk=pk)
    campana.activo = not campana.activo
    campana.save(update_fields=["activo"])
    messages.success(
        request,
        f"Campaña {campana} " + ("reabierta." if campana.activo else "cerrada: ya no recibe inscripciones."),
    )
    return redirect("beneficios:campana_lista")
