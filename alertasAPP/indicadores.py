"""
SGR - EVA 3
Alertas de registros sospechosos (R6: «no registrar solo para generar puntaje»).

Responsable original: Orlando Iribarren (tarea desarrollada por Ignacio Figueroa).

La fuente solo indica que la matriz debe distinguir el trabajo real del
registro hecho para cumplir. Se usan cuatro indicadores calculados con los
datos que el sistema ya guarda, siempre para un mismo funcionario:

  1. Contacto repetido: el mismo vecino (teléfono o RUT) en varios
     registros que suman puntaje dentro de la misma semana.
  2. Ráfaga de ingresos: muchos registros ingresados en pocos minutos
     (carga en bloque en vez de registrar a diario).
  3. Detalle copiado: el mismo texto de detalle en varios registros que
     suman puntaje dentro de la misma semana.
  4. Cupo diario al máximo: varios días de la misma semana con el máximo de
     ingresos permitido (R3).

Una alerta no cambia el puntaje ni rechaza nada: avisa al delegado qué
registros revisar en la verificación. Los umbrales se configuran con
variables de entorno (ver settings.py y .env.example).

Las funciones de este módulo son puras: reciben registros ya filtrados y no
consultan la base de datos, para poder probarlas con casos de borde.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from actividadesAPP.models import ZONA_CHILE, nombre_comparable, normalizar_telefono


CONTACTO_REPETIDO = "CONTACTO_REPETIDO"
RAFAGA = "RAFAGA"
DETALLE_COPIADO = "DETALLE_COPIADO"
CUPO_MAXIMO = "CUPO_MAXIMO"

INDICADORES = [
    (CONTACTO_REPETIDO, "Contacto repetido"),
    (RAFAGA, "Ráfaga de ingresos"),
    (DETALLE_COPIADO, "Detalle copiado"),
    (CUPO_MAXIMO, "Cupo diario al máximo"),
]
NOMBRES = dict(INDICADORES)

# El detalle debe tener al menos este largo para compararlo: textos muy
# cortos («ok», «visita») se repiten de forma natural.
LARGO_MINIMO_DETALLE = 15


@dataclass(frozen=True)
class Umbrales:
    contacto: int = 3
    rafaga: int = 5
    rafaga_minutos: int = 10
    detalle: int = 3
    cupo_dias: int = 3
    maximo_diario: int = 7

    @classmethod
    def desde_settings(cls):
        return cls(
            contacto=int(getattr(settings, "SGR_ALERTA_CONTACTO", 3)),
            rafaga=int(getattr(settings, "SGR_ALERTA_RAFAGA", 5)),
            rafaga_minutos=int(getattr(settings, "SGR_ALERTA_RAFAGA_MINUTOS", 10)),
            detalle=int(getattr(settings, "SGR_ALERTA_DETALLE", 3)),
            cupo_dias=int(getattr(settings, "SGR_ALERTA_CUPO_DIAS", 3)),
            maximo_diario=int(getattr(settings, "MAX_INGRESOS_DIARIOS", 7)),
        )

    def __post_init__(self):
        for nombre in ("contacto", "rafaga", "rafaga_minutos", "detalle", "cupo_dias", "maximo_diario"):
            if getattr(self, nombre) < 1:
                raise ValueError(f"El umbral «{nombre}» debe ser 1 o mayor.")


@dataclass
class Alerta:
    indicador: str
    funcionario: object
    semana: object  # lunes de la semana (fecha_actividad o de ingreso)
    descripcion: str
    registros: list = field(default_factory=list)

    @property
    def nombre(self):
        return NOMBRES[self.indicador]

    @property
    def cantidad(self):
        return len(self.registros)


def lunes_de(fecha):
    return fecha - timedelta(days=fecha.weekday())


def fecha_local(momento):
    return timezone.localtime(momento, ZONA_CHILE)


def clave_contacto(registro):
    """RUT si existe; si no, el teléfono normalizado. Sin datos, no se compara."""
    rut = (getattr(registro, "rut_usuario", "") or "").replace(".", "").replace("-", "").upper()
    if rut:
        return f"RUT:{rut}"
    telefono = normalizar_telefono(registro.telefono_usuario)
    return f"TEL:{telefono}" if len(telefono) >= 8 else None


def agrupar(registros, clave):
    grupos = defaultdict(list)
    for registro in registros:
        valor = clave(registro)
        if valor is not None:
            grupos[valor].append(registro)
    return grupos


# ============================================================
# 1. CONTACTO REPETIDO
# ============================================================

def contacto_repetido(registros, umbrales):
    alertas = []
    que_suman = [r for r in registros if r.puntua]
    grupos = agrupar(
        que_suman,
        lambda r: (
            (r.funcionario_id, lunes_de(r.fecha_actividad), clave_contacto(r))
            if clave_contacto(r) else None
        ),
    )
    for (_, semana, contacto), grupo in grupos.items():
        if len(grupo) >= umbrales.contacto:
            vecino = grupo[0].nombre_usuario or "el mismo vecino"
            alertas.append(Alerta(
                CONTACTO_REPETIDO, grupo[0].funcionario, semana,
                f"{len(grupo)} registros que suman puntaje con {vecino} "
                f"({'RUT' if contacto.startswith('RUT') else 'teléfono'} repetido) en la semana.",
                ordenar(grupo),
            ))
    return alertas


# ============================================================
# 2. RÁFAGA DE INGRESOS
# ============================================================

def rafaga(registros, umbrales):
    """
    Ventana deslizante sobre la fecha de ingreso: si dentro de
    `rafaga_minutos` hay `rafaga` o más ingresos, se informa la ráfaga más
    larga que los contiene (una sola alerta por ráfaga).
    """
    alertas = []
    ventana = timedelta(minutes=umbrales.rafaga_minutos)
    for _, grupo in agrupar(registros, lambda r: r.funcionario_id).items():
        grupo = ordenar(grupo)

        # 1) Marcar cada registro que forma parte de alguna ventana con
        #    `rafaga` o más ingresos.
        marcados = set()
        inicio = 0
        for fin in range(len(grupo)):
            while grupo[fin].fecha_ingreso - grupo[inicio].fecha_ingreso > ventana:
                inicio += 1
            if fin - inicio + 1 >= umbrales.rafaga:
                marcados.update(range(inicio, fin + 1))

        # 2) Unir marcados consecutivos en tramos; un salto mayor que la
        #    ventana separa dos ráfagas distintas.
        tramo = []
        for i in sorted(marcados):
            if tramo and (i != tramo[-1] + 1 or grupo[i].fecha_ingreso - grupo[tramo[-1]].fecha_ingreso > ventana):
                alertas.append(_alerta_rafaga([grupo[j] for j in tramo], umbrales))
                tramo = []
            tramo.append(i)
        if tramo:
            alertas.append(_alerta_rafaga([grupo[j] for j in tramo], umbrales))
    return alertas


def _alerta_rafaga(tramo, umbrales):
    primero, ultimo = fecha_local(tramo[0].fecha_ingreso), fecha_local(tramo[-1].fecha_ingreso)
    minutos = int((tramo[-1].fecha_ingreso - tramo[0].fecha_ingreso).total_seconds() // 60)
    return Alerta(
        RAFAGA, tramo[0].funcionario, lunes_de(primero.date()),
        f"{len(tramo)} registros ingresados en {minutos} minutos "
        f"({primero:%d-%m-%Y %H:%M} a {ultimo:%H:%M}); el umbral es {umbrales.rafaga} "
        f"en {umbrales.rafaga_minutos} minutos.",
        list(tramo),
    )


# ============================================================
# 3. DETALLE COPIADO
# ============================================================

def detalle_copiado(registros, umbrales):
    alertas = []

    def clave(r):
        texto = nombre_comparable(r.detalle)
        if not r.puntua or len(texto) < LARGO_MINIMO_DETALLE:
            return None
        return (r.funcionario_id, lunes_de(r.fecha_actividad), texto)

    for (_, semana, texto), grupo in agrupar(registros, clave).items():
        if len(grupo) >= umbrales.detalle:
            muestra = grupo[0].detalle.strip()
            if len(muestra) > 60:
                muestra = muestra[:57] + "…"
            alertas.append(Alerta(
                DETALLE_COPIADO, grupo[0].funcionario, semana,
                f"{len(grupo)} registros que suman puntaje con el mismo detalle: «{muestra}».",
                ordenar(grupo),
            ))
    return alertas


# ============================================================
# 4. CUPO DIARIO AL MÁXIMO
# ============================================================

def cupo_maximo(registros, umbrales):
    """Días (por fecha de ingreso, como R3) en que se usó el cupo completo."""
    alertas = []
    por_dia = agrupar(registros, lambda r: (r.funcionario_id, fecha_local(r.fecha_ingreso).date()))
    dias_llenos = defaultdict(list)
    for (funcionario_id, dia), grupo in por_dia.items():
        if len(grupo) >= umbrales.maximo_diario:
            dias_llenos[(funcionario_id, lunes_de(dia))].append((dia, grupo))

    for (_, semana), dias in dias_llenos.items():
        if len(dias) >= umbrales.cupo_dias:
            dias.sort(key=lambda par: par[0])
            fechas = ", ".join(f"{dia:%d-%m}" for dia, _ in dias)
            registros_semana = [r for _, grupo in dias for r in grupo]
            alertas.append(Alerta(
                CUPO_MAXIMO, dias[0][1][0].funcionario, semana,
                f"{len(dias)} días de la semana con el máximo de {umbrales.maximo_diario} "
                f"ingresos ({fechas}).",
                ordenar(registros_semana),
            ))
    return alertas


def ordenar(registros):
    return sorted(registros, key=lambda r: (r.fecha_ingreso, r.pk or 0))


DETECTORES = {
    CONTACTO_REPETIDO: contacto_repetido,
    RAFAGA: rafaga,
    DETALLE_COPIADO: detalle_copiado,
    CUPO_MAXIMO: cupo_maximo,
}


def detectar(registros, umbrales=None, indicadores=None):
    """Aplica los indicadores pedidos (todos por defecto) y ordena las alertas."""
    umbrales = umbrales or Umbrales.desde_settings()
    registros = list(registros)
    alertas = []
    for indicador in indicadores or DETECTORES:
        alertas.extend(DETECTORES[indicador](registros, umbrales))
    alertas.sort(key=lambda a: (-a.semana.toordinal(), str(a.funcionario), a.indicador))
    return alertas
