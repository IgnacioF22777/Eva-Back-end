"""
SGR - EVA 3
Dashboard de la delegación con gráficos (pauta, Actividad 1).

Responsable: Ignacio Figueroa.

Muestra, por delegación y por funcionario: avance y cumplimiento frente al
objetivo al día (semáforo), estado de verificación de los registros, carga
de trabajo, tendencia semanal, tubo de seguimiento y estado de los
compromisos. Permite filtrar por período, funcionario y rango de fechas.

Los gráficos se dibujan con HTML y CSS desde el servidor (sin librerías
externas): funcionan sin conexión a internet y cada valor también queda
escrito como texto, de modo que se leen sin depender del color.
"""

from datetime import timedelta
from decimal import Decimal

from django.db.models import Count
from django.shortcuts import render
from django.utils import timezone

from actividadesAPP.models import ZONA_CHILE, RegistroActividad
from actividadesAPP.seguimiento import entero_o_none, fecha_o_none
from seguridadAPP.models import PerfilUsuario
from seguridadAPP.perfiles import ADMINISTRADOR, SUPERVISOR, perfil_requerido
from tubo_gestionAPP.ambito import es_global
from tubo_gestionAPP.models import Compromiso
from delegacionesAPP.models import Delegacion

from .calculo import NARANJO, ROJO, VERDE, calcular_resumen_equipo
from .views import elegir_delegacion, elegir_periodo


COLORES_SEMAFORO = {
    VERDE: "#198754",
    NARANJO: "#fd7e14",
    ROJO: "#C41230",
}

COLORES_VERIFICACION = {
    RegistroActividad.APROBADA: "#198754",
    RegistroActividad.PENDIENTE: "#6c757d",
    RegistroActividad.ANTECEDENTES: "#ffc107",
    RegistroActividad.RECHAZADA: "#C41230",
}

COLORES_TUBO = {
    RegistroActividad.TUBO_SOLUCIONADO: "#198754",
    RegistroActividad.TUBO_EN_PROCESO: "#ffc107",
    RegistroActividad.TUBO_DERIVADO: "#0dcaf0",
    RegistroActividad.TUBO_NO_APLICA: "#adb5bd",
}

COLORES_COMPROMISO = {"verde": "#198754", "amarillo": "#ffc107", "rojo": "#C41230"}

SEMANAS_TENDENCIA = 10


def porcentaje(parte, total):
    return round(parte * 100 / total, 1) if total else 0


def dona(conteos, nombres, colores):
    """Segmentos de un gráfico de dona (conic-gradient) con su leyenda."""
    total = sum(conteos.values())
    segmentos, leyenda, acumulado = [], [], 0.0
    for clave, nombre in nombres:
        cantidad = conteos.get(clave, 0)
        pct = porcentaje(cantidad, total)
        if cantidad:
            segmentos.append(f"{colores[clave]} {acumulado}% {acumulado + pct}%")
        acumulado += pct
        leyenda.append({"nombre": nombre, "total": cantidad, "pct": pct, "color": colores[clave]})
    gradiente = ", ".join(segmentos) if segmentos else "#e9ecef 0% 100%"
    return {"total": total, "gradiente": gradiente, "leyenda": leyenda}


def tendencia_semanal(registros, hasta):
    """Registros por semana (lunes a domingo) en las últimas semanas."""
    lunes_actual = hasta - timedelta(days=hasta.weekday())
    semanas = [lunes_actual - timedelta(weeks=n) for n in range(SEMANAS_TENDENCIA - 1, -1, -1)]
    inicio = semanas[0]

    por_dia = dict(
        registros.filter(fecha_actividad__gte=inicio, fecha_actividad__lte=hasta)
        .values_list("fecha_actividad")
        .annotate(total=Count("id"))
    )
    aprobados_dia = dict(
        registros.filter(
            fecha_actividad__gte=inicio,
            fecha_actividad__lte=hasta,
            estado_verificacion=RegistroActividad.APROBADA,
        )
        .values_list("fecha_actividad")
        .annotate(total=Count("id"))
    )

    columnas = []
    for lunes in semanas:
        dias = [lunes + timedelta(days=d) for d in range(7)]
        total = sum(por_dia.get(dia, 0) for dia in dias)
        aprobados = sum(aprobados_dia.get(dia, 0) for dia in dias)
        columnas.append({"lunes": lunes, "total": total, "aprobados": aprobados})

    maximo = max([c["total"] for c in columnas] + [1])
    for columna in columnas:
        columna["alto"] = porcentaje(columna["total"], maximo)
        columna["alto_aprobados"] = porcentaje(columna["aprobados"], maximo)
    return columnas


@perfil_requerido(ADMINISTRADOR, SUPERVISOR)
def dashboard(request):
    hoy = timezone.localdate(timezone.now(), timezone=ZONA_CHILE)
    periodos, periodo = elegir_periodo(request.GET.get("periodo"), hoy)
    delegacion = elegir_delegacion(request.user, request.GET.get("delegacion"))

    contexto = {
        "periodos": periodos,
        "periodo": periodo,
        "delegacion": delegacion,
        "delegaciones": Delegacion.objects.filter(activo=True) if es_global(request.user) else None,
        "fecha_actual": hoy,
    }
    if periodo is None or delegacion is None:
        return render(request, "puntaje_equipo/dashboard.html", contexto)

    funcionarios = (
        PerfilUsuario.objects.filter(delegacion=delegacion, usuario__is_active=True)
        .select_related("usuario", "cargo", "delegacion")
        .order_by("usuario__first_name", "usuario__last_name")
    )

    funcionario_id = entero_o_none(request.GET.get("funcionario"))
    desde = fecha_o_none(request.GET.get("desde")) or periodo.fecha_inicio
    hasta = fecha_o_none(request.GET.get("hasta")) or min(periodo.fecha_fin, hoy)
    if hasta < desde:
        desde, hasta = hasta, desde

    # ---- Cumplimiento por funcionario (semáforo) ----
    resumen = calcular_resumen_equipo(funcionarios, periodo, hoy)
    filas = [f for f in resumen.filas if not funcionario_id or f.funcionario.pk == funcionario_id]
    escala = max([Decimal("120")] + [f.puntaje for f in filas])
    barras_cumplimiento = [
        {
            "nombre": fila.funcionario.usuario.get_full_name() or fila.funcionario.usuario.username,
            "cargo": fila.cargo.nombre if fila.cargo else "Sin cargo",
            "puntaje": fila.puntaje,
            "ancho": float(fila.puntaje / escala * 100),
            "color": COLORES_SEMAFORO.get(fila.semaforo, "#adb5bd"),
            "semaforo": fila.semaforo,
            "etiqueta": fila.etiqueta_semaforo,
            "tiene_metas": fila.tiene_metas,
        }
        for fila in filas
    ]
    posicion_objetivo = float(resumen.objetivo / escala * 100)

    # ---- Registros del rango ----
    registros = RegistroActividad.objects.filter(
        funcionario__delegacion=delegacion,
        activo=True,
        fecha_actividad__gte=desde,
        fecha_actividad__lte=hasta,
    )
    if funcionario_id:
        registros = registros.filter(funcionario_id=funcionario_id)

    verificacion = dona(
        dict(registros.values_list("estado_verificacion").annotate(t=Count("id"))),
        RegistroActividad.ESTADOS_VERIFICACION,
        COLORES_VERIFICACION,
    )

    tubo_registros = registros.filter(ingresa_tubo=True)
    tubo = dona(
        dict(tubo_registros.values_list("estado_tubo").annotate(t=Count("id"))),
        RegistroActividad.ESTADOS_TUBO,
        COLORES_TUBO,
    )
    tubo_aplica = tubo_registros.exclude(estado_tubo=RegistroActividad.TUBO_NO_APLICA).count()
    tubo["soluciones"] = porcentaje(
        tubo_registros.filter(estado_tubo=RegistroActividad.TUBO_SOLUCIONADO).count(), tubo_aplica,
    )
    tubo["emergencias"] = tubo_registros.filter(es_emergencia=True).count()

    # ---- Carga de trabajo (registros por funcionario y estado) ----
    carga_cruda = (
        registros.values("funcionario_id", "estado_verificacion").annotate(total=Count("id"))
    )
    carga = {}
    for fila in carga_cruda:
        carga.setdefault(fila["funcionario_id"], {})[fila["estado_verificacion"]] = fila["total"]
    maximo_carga = max([sum(v.values()) for v in carga.values()] + [1])
    barras_carga = []
    for funcionario in funcionarios:
        if funcionario_id and funcionario.pk != funcionario_id:
            continue
        datos = carga.get(funcionario.pk, {})
        total = sum(datos.values())
        barras_carga.append({
            "nombre": funcionario.usuario.get_full_name() or funcionario.usuario.username,
            "total": total,
            "tramos": [
                {
                    "nombre": nombre,
                    "total": datos.get(clave, 0),
                    "ancho": porcentaje(datos.get(clave, 0), maximo_carga),
                    "color": COLORES_VERIFICACION[clave],
                }
                for clave, nombre in RegistroActividad.ESTADOS_VERIFICACION
                if datos.get(clave, 0)
            ],
        })
    barras_carga.sort(key=lambda b: -b["total"])

    # ---- Compromisos de la delegación ----
    compromisos = dona(
        dict(
            Compromiso.objects.filter(delegacion=delegacion, activo=True)
            .values_list("estado")
            .annotate(t=Count("id"))
        ),
        Compromiso.ESTADOS,
        COLORES_COMPROMISO,
    )

    base_tendencia = RegistroActividad.objects.filter(funcionario__delegacion=delegacion, activo=True)
    if funcionario_id:
        base_tendencia = base_tendencia.filter(funcionario_id=funcionario_id)

    total_registros = registros.count()
    aprobados = registros.filter(estado_verificacion=RegistroActividad.APROBADA).count()
    contexto.update({
        "funcionarios": funcionarios,
        "funcionario_id": funcionario_id,
        "desde": desde,
        "hasta": hasta,
        "resumen": resumen,
        "barras_cumplimiento": barras_cumplimiento,
        "posicion_objetivo": posicion_objetivo,
        "verificacion": verificacion,
        "tubo": tubo,
        "barras_carga": barras_carga,
        # La tendencia mira las últimas semanas hasta la fecha «hasta»,
        # aunque el rango elegido sea más corto.
        "tendencia": tendencia_semanal(base_tendencia, hasta),
        "compromisos": compromisos,
        "kpi": {
            "registros": total_registros,
            "aprobados": aprobados,
            "pct_aprobados": porcentaje(aprobados, total_registros),
            "pendientes": registros.filter(estado_verificacion=RegistroActividad.PENDIENTE).count(),
            "puntaje_promedio": resumen.puntaje_promedio,
            "objetivo": resumen.objetivo,
        },
    })
    return render(request, "puntaje_equipo/dashboard.html", contexto)
