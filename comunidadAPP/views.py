from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_GET, require_POST

from delegacionesAPP.models import Delegacion
from organizacionesAPP.models import OrganizacionComunitaria
from seguridadAPP.models import normalizar_rut
from tubo_gestionAPP.ambito import delegacion_id_de, es_global

from .forms import HitoForm, MembresiaForm, TerritorioForm, VecinoForm
from .models import Hito, MembresiaJunta, Territorio, Vecino


POR_PAGINA = 50

FUERA_DE_AMBITO = (
    "El registro pertenece a otra delegación: su perfil solo puede "
    "operar los registros de su delegación."
)


# ============================================================
# ÁMBITO POR DELEGACIÓN (mismo criterio que el resto del SGR)
# ============================================================

def en_ambito(usuario, queryset, campo="delegacion_id"):
    """El Administrador ve todo; el resto, solo su delegación (o nada)."""
    if es_global(usuario):
        return queryset
    propia = delegacion_id_de(usuario)
    return queryset.filter(**{campo: propia}) if propia else queryset.none()


def verificar_ambito(usuario, delegacion_id):
    if not es_global(usuario) and (delegacion_id is None or delegacion_id != delegacion_id_de(usuario)):
        raise PermissionDenied(FUERA_DE_AMBITO)


def volver(request, por_defecto, *args):
    destino = request.POST.get("volver", "")
    if destino and url_has_allowed_host_and_scheme(
        destino, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return redirect(destino)
    return redirect(por_defecto, *args)


def filtro_estado(request, queryset):
    estado = request.GET.get("estado", "activos")
    if estado == "activos":
        return queryset.filter(activo=True), estado
    if estado == "inactivos":
        return queryset.filter(activo=False), estado
    return queryset, "todos"


def filtro_delegacion(request, queryset):
    """Solo el Administrador filtra por delegación desde la URL."""
    if es_global(request.user):
        delegacion = request.GET.get("delegacion", "")
        delegaciones = Delegacion.objects.order_by("nombre")
        if delegacion.isdigit():
            queryset = queryset.filter(delegacion_id=int(delegacion))
        else:
            delegacion = ""
    else:
        propia = delegacion_id_de(request.user)
        delegacion = str(propia) if propia else ""
        delegaciones = Delegacion.objects.filter(pk=propia)
    return queryset, delegacion, delegaciones


def paginar(request, queryset):
    pagina = Paginator(queryset, POR_PAGINA).get_page(request.GET.get("pagina"))
    parametros = request.GET.copy()
    parametros.pop("pagina", None)
    return pagina, parametros.urlencode()


def guardar_formulario(request, form_class, plantilla, titulo, lista, instancia=None, mensaje="", **extra):
    if request.method == "POST":
        form = form_class(request.POST, instance=instancia, usuario=request.user)
        if form.is_valid():
            objeto = form.save(commit=False)
            verificar_ambito(request.user, objeto.delegacion_id)
            if hasattr(objeto, "creado_por_id") and not objeto.pk:
                objeto.creado_por = request.user
            objeto.save()
            messages.success(request, mensaje.format(objeto=objeto))
            return redirect(lista)
    else:
        form = form_class(instance=instancia, usuario=request.user)

    return render(request, plantilla, {"form": form, "titulo": titulo, "lista": lista, **extra})


# ============================================================
# MANTENEDOR: TERRITORIOS
# ============================================================

@login_required
@permission_required("comunidadAPP.view_territorio", raise_exception=True)
def territorio_lista(request):
    busqueda = request.GET.get("q", "").strip()
    territorios = en_ambito(request.user, Territorio.objects.select_related("delegacion"))
    territorios, delegacion, delegaciones = filtro_delegacion(request, territorios)
    territorios, estado = filtro_estado(request, territorios)

    if busqueda:
        territorios = territorios.filter(
            Q(nombre__icontains=busqueda) | Q(descripcion__icontains=busqueda)
        )

    territorios = territorios.annotate(
        total_vecinos=Count("vecinos", filter=Q(vecinos__activo=True), distinct=True),
        total_hitos=Count("hitos", filter=Q(hitos__activo=True), distinct=True),
    ).order_by("delegacion__nombre", "nombre")

    pagina, parametros = paginar(request, territorios)
    return render(request, "comunidad/territorio_lista.html", {
        "pagina": pagina,
        "parametros": parametros,
        "busqueda": busqueda,
        "estado": estado,
        "delegacion": delegacion,
        "delegaciones": delegaciones,
        "vision_global": es_global(request.user),
    })


@login_required
@permission_required("comunidadAPP.add_territorio", raise_exception=True)
def territorio_crear(request):
    return guardar_formulario(
        request, TerritorioForm, "comunidad/formulario.html", "Registrar territorio",
        "comunidad:territorio_lista", mensaje="Territorio «{objeto.nombre}» registrado correctamente.",
    )


@login_required
@permission_required("comunidadAPP.change_territorio", raise_exception=True)
def territorio_editar(request, pk):
    territorio = get_object_or_404(Territorio, pk=pk)
    verificar_ambito(request.user, territorio.delegacion_id)
    return guardar_formulario(
        request, TerritorioForm, "comunidad/formulario.html", f"Editar territorio: {territorio.nombre}",
        "comunidad:territorio_lista", instancia=territorio, mensaje="Territorio actualizado correctamente.",
    )


@login_required
@permission_required("comunidadAPP.delete_territorio", raise_exception=True)
@require_POST
def territorio_cambiar_estado(request, pk):
    territorio = get_object_or_404(Territorio, pk=pk)
    verificar_ambito(request.user, territorio.delegacion_id)

    if territorio.activo:
        en_uso = (
            territorio.vecinos.filter(activo=True).exists()
            or territorio.hitos.filter(activo=True).exists()
        )
        if en_uso:
            messages.error(
                request,
                "No se puede dar de baja: el territorio tiene vecinos o hitos vigentes. "
                "Reasígnelos o délos de baja primero.",
            )
            return volver(request, "comunidad:territorio_lista")

    territorio.activo = not territorio.activo
    territorio.save(update_fields=["activo"])
    messages.success(
        request,
        "Territorio reactivado." if territorio.activo
        else "Territorio dado de baja. Puede reactivarlo cuando sea necesario.",
    )
    return volver(request, "comunidad:territorio_lista")


# ============================================================
# MANTENEDOR: VECINOS
# ============================================================

@login_required
@permission_required("comunidadAPP.view_vecino", raise_exception=True)
def vecino_lista(request):
    busqueda = request.GET.get("q", "").strip()
    vecinos = en_ambito(request.user, Vecino.objects.select_related("delegacion", "territorio"))
    vecinos, delegacion, delegaciones = filtro_delegacion(request, vecinos)
    vecinos, estado = filtro_estado(request, vecinos)

    territorio = request.GET.get("territorio", "")
    if territorio.isdigit():
        vecinos = vecinos.filter(territorio_id=int(territorio))
    else:
        territorio = ""

    if busqueda:
        rut = normalizar_rut(busqueda)
        vecinos = vecinos.filter(
            Q(nombre__icontains=busqueda)
            | Q(rut__icontains=rut)
            | Q(telefono__icontains=busqueda)
            | Q(direccion__icontains=busqueda)
        )

    vecinos = vecinos.annotate(
        total_membresias=Count("membresias", filter=Q(membresias__activo=True))
    ).order_by("nombre")

    pagina, parametros = paginar(request, vecinos)
    return render(request, "comunidad/vecino_lista.html", {
        "pagina": pagina,
        "parametros": parametros,
        "busqueda": busqueda,
        "estado": estado,
        "delegacion": delegacion,
        "delegaciones": delegaciones,
        "territorio": territorio,
        "territorios": en_ambito(request.user, Territorio.objects.filter(activo=True)),
        "vision_global": es_global(request.user),
    })


@login_required
@permission_required("comunidadAPP.add_vecino", raise_exception=True)
def vecino_crear(request):
    return guardar_formulario(
        request, VecinoForm, "comunidad/formulario.html", "Registrar vecino/a",
        "comunidad:vecino_lista", mensaje="Vecino/a «{objeto.nombre}» registrado correctamente.",
    )


@login_required
@permission_required("comunidadAPP.change_vecino", raise_exception=True)
def vecino_editar(request, pk):
    vecino = get_object_or_404(Vecino, pk=pk)
    verificar_ambito(request.user, vecino.delegacion_id)
    return guardar_formulario(
        request, VecinoForm, "comunidad/formulario.html", f"Editar vecino/a: {vecino.nombre}",
        "comunidad:vecino_lista", instancia=vecino, mensaje="Datos del vecino/a actualizados correctamente.",
        membresias=vecino.membresias.select_related("organizacion").order_by("-activo", "-fecha_inicio"),
    )


@login_required
@permission_required("comunidadAPP.delete_vecino", raise_exception=True)
@require_POST
def vecino_cambiar_estado(request, pk):
    vecino = get_object_or_404(Vecino, pk=pk)
    verificar_ambito(request.user, vecino.delegacion_id)

    if vecino.activo and vecino.membresias.filter(activo=True).exists():
        messages.error(
            request,
            "No se puede dar de baja: el vecino tiene membresías vigentes en organizaciones. "
            "Ciérrelas primero (fecha de término).",
        )
        return volver(request, "comunidad:vecino_lista")

    vecino.activo = not vecino.activo
    vecino.save(update_fields=["activo"])
    messages.success(
        request,
        "Vecino/a reactivado." if vecino.activo
        else "Vecino/a dado de baja. Puede reactivarlo cuando sea necesario.",
    )
    return volver(request, "comunidad:vecino_lista")


@login_required
@permission_required("comunidadAPP.view_vecino", raise_exception=True)
@require_GET
def vecino_buscar(request):
    """
    Autocompletado: devuelve los datos de un vecino por su RUT, para que
    los formularios de actividades y atención social no los vuelvan a
    pedir. Respeta el ámbito por delegación.
    """
    rut = normalizar_rut(request.GET.get("rut", ""))
    vecino = None
    if len(rut) >= 3:
        vecino = en_ambito(request.user, Vecino.objects.filter(rut=rut, activo=True)).first()

    if vecino is None:
        return JsonResponse({"encontrado": False})

    return JsonResponse({
        "encontrado": True,
        "rut": vecino.rut_formateado,
        "nombre": vecino.nombre,
        "telefono": vecino.telefono,
        "correo": vecino.correo,
        "direccion": vecino.direccion,
    })


# ============================================================
# MEMBRESÍA Y DIRIGENCIA EN JUNTAS DE VECINOS
# ============================================================

def obtener_organizacion(usuario, pk):
    organizacion = get_object_or_404(OrganizacionComunitaria, pk=pk)
    verificar_ambito(usuario, organizacion.delegacion_id)
    return organizacion


@login_required
@permission_required("comunidadAPP.view_membresiajunta", raise_exception=True)
def membresia_lista(request, organizacion_pk):
    organizacion = obtener_organizacion(request.user, organizacion_pk)
    membresias = organizacion.membresias.select_related("vecino")

    vigentes = membresias.filter(activo=True)
    return render(request, "comunidad/membresia_lista.html", {
        "organizacion": organizacion,
        "directiva": vigentes.filter(tipo=MembresiaJunta.DIRIGENTE).order_by("cargo", "vecino__nombre"),
        "socios": vigentes.filter(tipo=MembresiaJunta.SOCIO).order_by("vecino__nombre"),
        "historial": membresias.filter(activo=False).order_by("-fecha_termino", "vecino__nombre"),
    })


@login_required
@permission_required("comunidadAPP.add_membresiajunta", raise_exception=True)
def membresia_crear(request, organizacion_pk):
    organizacion = obtener_organizacion(request.user, organizacion_pk)
    if not organizacion.activo:
        raise PermissionDenied("La organización está dada de baja: no admite nuevas membresías.")

    instancia = MembresiaJunta(organizacion=organizacion)
    form = MembresiaForm(request.POST or None, instance=instancia, organizacion=organizacion)

    if request.method == "POST" and form.is_valid():
        membresia = form.save()
        messages.success(request, f"{membresia.vecino.nombre} quedó registrado/a en la organización.")
        return redirect("comunidad:membresia_lista", organizacion.pk)

    return render(request, "comunidad/formulario.html", {
        "form": form,
        "titulo": f"Agregar socio o dirigente: {organizacion.nombre}",
        "volver_a": ("comunidad:membresia_lista", organizacion.pk),
    })


@login_required
@permission_required("comunidadAPP.change_membresiajunta", raise_exception=True)
def membresia_editar(request, pk):
    membresia = get_object_or_404(MembresiaJunta.objects.select_related("organizacion", "vecino"), pk=pk)
    organizacion = obtener_organizacion(request.user, membresia.organizacion_id)

    form = MembresiaForm(request.POST or None, instance=membresia, organizacion=organizacion)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Membresía actualizada correctamente.")
        return redirect("comunidad:membresia_lista", organizacion.pk)

    return render(request, "comunidad/formulario.html", {
        "form": form,
        "titulo": f"Membresía de {membresia.vecino.nombre} en {organizacion.nombre}",
        "volver_a": ("comunidad:membresia_lista", organizacion.pk),
    })


@login_required
@permission_required("comunidadAPP.change_membresiajunta", raise_exception=True)
@require_POST
def membresia_cerrar(request, pk):
    """Cierra la membresía con fecha de hoy: queda en el historial."""
    membresia = get_object_or_404(MembresiaJunta, pk=pk)
    obtener_organizacion(request.user, membresia.organizacion_id)

    if membresia.activo:
        membresia.activo = False
        membresia.fecha_termino = max(date.today(), membresia.fecha_inicio)
        membresia.save(update_fields=["activo", "fecha_termino"])
        messages.success(request, "Membresía cerrada. Se conserva en el historial de la organización.")
    return redirect("comunidad:membresia_lista", membresia.organizacion_id)


# ============================================================
# MANTENEDOR: HITOS
# ============================================================

@login_required
@permission_required("comunidadAPP.view_hito", raise_exception=True)
def hito_lista(request):
    busqueda = request.GET.get("q", "").strip()
    hitos = en_ambito(
        request.user,
        Hito.objects.select_related("delegacion", "territorio", "organizacion", "responsable"),
    )
    hitos, delegacion, delegaciones = filtro_delegacion(request, hitos)
    hitos, estado = filtro_estado(request, hitos)

    situacion = request.GET.get("situacion", "")
    if situacion in dict(Hito.ESTADOS):
        hitos = hitos.filter(estado=situacion)
    elif situacion == "atrasados":
        hitos = hitos.filter(
            estado__in=[Hito.PENDIENTE, Hito.EN_CURSO], fecha_programada__lt=date.today()
        )
    else:
        situacion = ""

    responsable = request.GET.get("responsable", "")
    if responsable == "yo":
        hitos = hitos.filter(responsable=request.user)
    else:
        responsable = ""

    desde = request.GET.get("desde", "")
    hasta = request.GET.get("hasta", "")
    try:
        if desde:
            hitos = hitos.filter(fecha_programada__gte=date.fromisoformat(desde))
        if hasta:
            hitos = hitos.filter(fecha_programada__lte=date.fromisoformat(hasta))
    except ValueError:
        messages.error(request, "El rango de fechas no es válido.")
        desde = hasta = ""

    if busqueda:
        hitos = hitos.filter(
            Q(nombre__icontains=busqueda)
            | Q(descripcion__icontains=busqueda)
            | Q(responsable__first_name__icontains=busqueda)
            | Q(responsable__last_name__icontains=busqueda)
            | Q(organizacion__nombre__icontains=busqueda)
        )

    pagina, parametros = paginar(request, hitos.order_by("fecha_programada", "nombre"))
    return render(request, "comunidad/hito_lista.html", {
        "pagina": pagina,
        "parametros": parametros,
        "busqueda": busqueda,
        "estado": estado,
        "situacion": situacion,
        "responsable": responsable,
        "desde": desde,
        "hasta": hasta,
        "estados": Hito.ESTADOS,
        "delegacion": delegacion,
        "delegaciones": delegaciones,
        "vision_global": es_global(request.user),
    })


@login_required
@permission_required("comunidadAPP.add_hito", raise_exception=True)
def hito_crear(request):
    return guardar_formulario(
        request, HitoForm, "comunidad/formulario.html", "Registrar hito",
        "comunidad:hito_lista", mensaje="Hito «{objeto.nombre}» registrado correctamente.",
    )


@login_required
@permission_required("comunidadAPP.change_hito", raise_exception=True)
def hito_editar(request, pk):
    hito = get_object_or_404(Hito, pk=pk)
    verificar_ambito(request.user, hito.delegacion_id)
    return guardar_formulario(
        request, HitoForm, "comunidad/formulario.html", f"Editar hito: {hito.nombre}",
        "comunidad:hito_lista", instancia=hito, mensaje="Hito actualizado correctamente.",
    )


@login_required
@permission_required("comunidadAPP.delete_hito", raise_exception=True)
@require_POST
def hito_cambiar_estado(request, pk):
    hito = get_object_or_404(Hito, pk=pk)
    verificar_ambito(request.user, hito.delegacion_id)

    hito.activo = not hito.activo
    hito.save(update_fields=["activo"])
    messages.success(
        request,
        "Hito reactivado." if hito.activo else "Hito dado de baja. Puede reactivarlo cuando sea necesario.",
    )
    return volver(request, "comunidad:hito_lista")
