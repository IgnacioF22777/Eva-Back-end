"""Verificación de actividades y tubo de seguimiento por delegación (Eva 3).

Pauta de la Evaluación 3:

- Flujo de verificación de actividades y evidencias con estados pendiente,
  aprobada, rechazada o solicitud de más antecedentes. Un registro
  aprobado no permite modificaciones.
- Tubo de seguimiento por delegación: todos los funcionarios de la
  delegación lo consultan, pero cada uno solo modifica sus propios
  registros mientras no estén aprobados.
- Búsqueda dinámica en el Tubo por código, RUT o nombre del solicitante al
  escribir; filtros por funcionario, rango de fechas y estado.

Ámbito:
    Administrador  -> todas las delegaciones (puede filtrar por una).
    Supervisor     -> (delegado) su delegación; verifica a su equipo.
    Administrativo -> consulta el tubo de su delegación y opera lo propio.
"""

import os
from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Count, Q
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from delegacionesAPP.models import Delegacion
from seguridadAPP.models import PerfilUsuario, normalizar_rut
from seguridadAPP.perfiles import SUPERVISOR, perfil_de
from tubo_gestionAPP.ambito import SIN_DELEGACION, delegacion_id_de, es_global

from .models import RegistroActividad
from .views import obtener_funcionario


# ============================================================
# ÁMBITO
# ============================================================

def registros_de_delegacion(usuario):
    """Registros de la delegación del usuario (todas, si es Administrador)."""
    registros = RegistroActividad.objects.select_related(
        "funcionario__usuario",
        "funcionario__delegacion",
        "actividad",
        "verificado_por",
    )
    if es_global(usuario):
        return registros

    delegacion_id = delegacion_id_de(usuario)
    if delegacion_id is None:
        raise PermissionDenied(SIN_DELEGACION)
    return registros.filter(funcionario__delegacion_id=delegacion_id)


def puede_verificar(usuario, registro):
    """El delegado verifica a su equipo; nadie se verifica a sí mismo."""
    if not usuario.has_perm("actividadesAPP.verificar_registroactividad"):
        return False
    if registro.funcionario.usuario_id == usuario.pk:
        return False
    if es_global(usuario):
        return True
    return (
        perfil_de(usuario) == SUPERVISOR
        and delegacion_id_de(usuario) is not None
        and registro.funcionario.delegacion_id == delegacion_id_de(usuario)
    )


def funcionarios_del_ambito(usuario, delegacion=None):
    funcionarios = PerfilUsuario.objects.filter(usuario__is_active=True).select_related("usuario")
    if es_global(usuario):
        if delegacion is not None:
            funcionarios = funcionarios.filter(delegacion=delegacion)
    else:
        funcionarios = funcionarios.filter(delegacion_id=delegacion_id_de(usuario))
    return funcionarios.order_by("usuario__first_name", "usuario__last_name")


def fecha_o_none(valor):
    try:
        return date.fromisoformat((valor or "").strip())
    except ValueError:
        return None


def entero_o_none(valor):
    valor = (valor or "").strip()
    return int(valor) if valor.isdecimal() else None


def aplicar_filtros(request, registros, delegacion=None):
    """Filtros comunes: funcionario, rango de fechas y búsqueda."""
    filtros = {
        "q": request.GET.get("q", "").strip()[:60],
        "funcionario": entero_o_none(request.GET.get("funcionario")),
        "desde": fecha_o_none(request.GET.get("desde")),
        "hasta": fecha_o_none(request.GET.get("hasta")),
    }

    if delegacion is not None:
        registros = registros.filter(funcionario__delegacion=delegacion)
    if filtros["funcionario"]:
        registros = registros.filter(funcionario_id=filtros["funcionario"])
    if filtros["desde"]:
        registros = registros.filter(fecha_actividad__gte=filtros["desde"])
    if filtros["hasta"]:
        registros = registros.filter(fecha_actividad__lte=filtros["hasta"])

    texto = filtros["q"]
    if texto:
        condicion = (
            Q(codigo__icontains=texto)
            | Q(nombre_usuario__icontains=texto)
            | Q(rut_usuario__icontains=texto)
        )
        rut = normalizar_rut(texto)
        if len(rut) > 2:
            condicion |= Q(rut_usuario__icontains=rut.replace("-", ""))
            condicion |= Q(rut_usuario__icontains=rut)
        registros = registros.filter(condicion)

    return registros, filtros


def delegacion_elegida(request):
    """Solo el Administrador elige delegación; el resto queda en la propia."""
    if not es_global(request.user):
        return None
    pk = entero_o_none(request.GET.get("delegacion"))
    return get_object_or_404(Delegacion, pk=pk) if pk else None


def volver(request, por_defecto):
    destino = request.POST.get("siguiente", "")
    if destino and url_has_allowed_host_and_scheme(
        destino, allowed_hosts={request.get_host()}, require_https=request.is_secure(),
    ):
        return redirect(destino)
    return redirect(por_defecto)


# ============================================================
# VERIFICACIÓN (DELEGADO)
# ============================================================

@login_required
@permission_required("actividadesAPP.verificar_registroactividad", raise_exception=True)
def verificacion_lista(request):
    delegacion = delegacion_elegida(request)
    registros = registros_de_delegacion(request.user).filter(activo=True).exclude(
        funcionario__usuario=request.user
    )

    estado = request.GET.get("estado", RegistroActividad.PENDIENTE)
    estados = dict(RegistroActividad.ESTADOS_VERIFICACION)
    conteo_base = registros
    if delegacion is not None:
        conteo_base = conteo_base.filter(funcionario__delegacion=delegacion)
    conteo = dict(
        conteo_base.values_list("estado_verificacion").annotate(total=Count("id"))
    )

    if estado in estados:
        registros = registros.filter(estado_verificacion=estado)
    else:
        estado = "TODOS"

    registros, filtros = aplicar_filtros(request, registros, delegacion)

    return render(request, "actividades/verificacion_lista.html", {
        "registros": registros.order_by("fecha_actividad", "fecha_ingreso")[:300],
        "estado": estado,
        "estados": RegistroActividad.ESTADOS_VERIFICACION,
        "conteo": [
            {"clave": clave, "nombre": nombre, "total": conteo.get(clave, 0)}
            for clave, nombre in RegistroActividad.ESTADOS_VERIFICACION
        ],
        "filtros": filtros,
        "funcionarios": funcionarios_del_ambito(request.user, delegacion),
        "delegaciones": Delegacion.objects.filter(activo=True) if es_global(request.user) else None,
        "delegacion": delegacion,
    })


@login_required
@permission_required("actividadesAPP.verificar_registroactividad", raise_exception=True)
@require_POST
def actividad_verificar(request, pk):
    registro = get_object_or_404(registros_de_delegacion(request.user), pk=pk)
    if not puede_verificar(request.user, registro):
        raise PermissionDenied("No puede verificar este registro.")

    try:
        registro.verificar(
            request.user,
            request.POST.get("estado", ""),
            request.POST.get("observacion", ""),
        )
    except ValidationError as error:
        messages.error(request, " ".join(error.messages))
    else:
        messages.success(
            request,
            f"Registro {registro.codigo or registro.pk}: "
            f"{registro.get_estado_verificacion_display().lower()}.",
        )
    return volver(request, "actividades:verificacion")


# ============================================================
# TUBO DE SEGUIMIENTO (TODA LA DELEGACIÓN)
# ============================================================

@login_required
@permission_required("actividadesAPP.view_registroactividad", raise_exception=True)
def tubo(request):
    delegacion = delegacion_elegida(request)
    registros = registros_de_delegacion(request.user).filter(ingresa_tubo=True, activo=True)
    if delegacion is not None:
        registros = registros.filter(funcionario__delegacion=delegacion)

    resumen = dict(registros.values_list("estado_tubo").annotate(total=Count("id")))
    total = sum(resumen.values())
    solucionados = resumen.get(RegistroActividad.TUBO_SOLUCIONADO, 0)

    estado = request.GET.get("estado", "")
    if estado in dict(RegistroActividad.ESTADOS_TUBO):
        registros = registros.filter(estado_tubo=estado)
    else:
        estado = ""
    if request.GET.get("emergencia") == "1":
        registros = registros.filter(es_emergencia=True)

    registros, filtros = aplicar_filtros(request, registros)
    registros = registros.order_by("-fecha_actividad", "-fecha_ingreso")[:300]

    try:
        mi_perfil_id = request.user.perfil.pk
    except PerfilUsuario.DoesNotExist:
        mi_perfil_id = None

    contexto = {
        "registros": registros,
        "estado": estado,
        "estados": RegistroActividad.ESTADOS_TUBO,
        "solo_emergencias": request.GET.get("emergencia") == "1",
        "filtros": filtros,
        "funcionarios": funcionarios_del_ambito(request.user, delegacion),
        "delegaciones": Delegacion.objects.filter(activo=True) if es_global(request.user) else None,
        "delegacion": delegacion,
        "mi_perfil_id": mi_perfil_id,
        "resumen": [
            {"clave": clave, "nombre": nombre, "total": resumen.get(clave, 0)}
            for clave, nombre in RegistroActividad.ESTADOS_TUBO
        ],
        "total_tubo": total,
        "porcentaje_soluciones": round(solucionados * 100 / total, 1) if total else 0,
    }

    # Búsqueda dinámica: el navegador pide solo las filas al escribir.
    if request.GET.get("parcial") == "1":
        return render(request, "actividades/_tubo_filas.html", contexto)
    return render(request, "actividades/tubo.html", contexto)


@login_required
@permission_required("actividadesAPP.change_registroactividad", raise_exception=True)
@require_POST
def tubo_cambiar_estado(request, pk):
    """Solo el dueño del registro actualiza su seguimiento, si no está aprobado."""
    funcionario = obtener_funcionario(request.user)
    registro = get_object_or_404(RegistroActividad, pk=pk)
    if registro.funcionario_id != funcionario.pk:
        raise PermissionDenied("Solo puede actualizar el seguimiento de sus propios registros.")

    try:
        registro.cambiar_estado_tubo(request.POST.get("estado_tubo", ""))
    except ValidationError as error:
        messages.error(request, " ".join(error.messages))
    else:
        messages.success(
            request,
            f"{registro.codigo}: estado del tubo «{registro.get_estado_tubo_display()}».",
        )
    return volver(request, "actividades:tubo")


# ============================================================
# EVIDENCIAS (DESCARGA PROTEGIDA)
# ============================================================

@login_required
@permission_required("actividadesAPP.view_registroactividad", raise_exception=True)
def evidencia_descargar(request, pk):
    """La ven el dueño, el delegado de su delegación y el Administrador."""
    registro = get_object_or_404(RegistroActividad, pk=pk)
    if not registro.evidencia:
        raise Http404("El registro no tiene evidencia.")

    es_dueno = registro.funcionario.usuario_id == request.user.pk
    es_delegado = (
        perfil_de(request.user) == SUPERVISOR
        and delegacion_id_de(request.user) is not None
        and delegacion_id_de(request.user) == registro.funcionario.delegacion_id
    )
    if not (es_dueno or es_delegado or es_global(request.user)):
        raise PermissionDenied("No tiene acceso a esta evidencia.")

    try:
        archivo = registro.evidencia.open("rb")
    except FileNotFoundError as error:
        raise Http404("El archivo de evidencia no está disponible.") from error

    nombre = registro.evidencia_nombre or os.path.basename(registro.evidencia.name)
    return FileResponse(archivo, as_attachment=True, filename=nombre)
