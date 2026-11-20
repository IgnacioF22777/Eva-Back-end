"""
SGR - EVA 3
Puntaje del equipo (pantalla de la delegación, R10).

Responsable: Ignacio Figueroa.

Reproduce la hoja RESUMEN de la matriz Excel: por cada funcionario de la
delegación muestra su puntaje (avance), el objetivo esperado a la fecha,
el semáforo, el último ingreso y el promedio diario de ingresos; y al
final los totales del equipo.

No calcula puntajes por su cuenta: reutiliza «Mi matriz» y el resumen de
ingresos de José (actividadesAPP), para que la pantalla del equipo y la
individual muestren siempre los mismos números. No escribe en la base de
datos.
"""

from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP

from django.utils import timezone

from actividadesAPP.models import ZONA_CHILE
from actividadesAPP.puntajes import (
    dias_ausencia_en_periodo,
    obtener_dias_periodo,
    obtener_mi_matriz,
)
from actividadesAPP.resumen_ingresos import obtener_resumen_ingresos
from sgr_maestrosAPP.feriados import feriados_entre
from tubo_gestionAPP.validadores import calcular_dias_computables


CIEN = Decimal("100")
DOS_DECIMALES = Decimal("0.01")

# Hoja SEMAFORO del Excel: verde si el avance alcanza el objetivo del día;
# naranjo si llega al 60 % de ese objetivo; rojo bajo eso.
FACTOR_NARANJO = Decimal("0.6")

VERDE = "VERDE"
NARANJO = "NARANJO"
ROJO = "ROJO"
SIN_METAS = "SIN_METAS"

ETIQUETAS_SEMAFORO = {
    VERDE: "Verde",
    NARANJO: "Naranjo",
    ROJO: "Rojo",
    SIN_METAS: "Sin metas",
}


def redondear(valor):
    return Decimal(str(valor)).quantize(DOS_DECIMALES, rounding=ROUND_HALF_UP)


# ============================================================
# OBJETIVO AL DÍA DE HOY
# ============================================================

def dias_transcurridos(periodo, fecha_referencia):
    """Días hábiles del período ya transcurridos (hoy incluido, sin feriados)."""
    if fecha_referencia < periodo.fecha_inicio:
        return 0

    corte = min(periodo.fecha_fin, fecha_referencia)
    return calcular_dias_computables(
        periodo.fecha_inicio,
        corte,
        feriados_entre(periodo.fecha_inicio, corte),
    )


def calcular_objetivo_al_dia(dias_pasados, dias_periodo, dias_ausencia=0):
    """
    Porcentaje del período que ya debería estar cumplido.

    Excel (SEMAFORO, columna K): (días transcurridos − ausencias) / días
    del período. Se expresa de 0 a 100 para compararlo con el puntaje.
    """
    if dias_pasados < 0 or dias_periodo < 0 or dias_ausencia < 0:
        raise ValueError("Los días no pueden ser negativos.")

    if dias_periodo == 0:
        return Decimal("0.00")

    efectivos = max(min(dias_pasados, dias_periodo) - dias_ausencia, 0)
    return redondear(Decimal(efectivos) * CIEN / Decimal(dias_periodo))


def calcular_semaforo(avance, objetivo):
    """Color según la fórmula de la hoja SEMAFORO."""
    avance = Decimal(str(avance))
    objetivo = Decimal(str(objetivo))

    if avance < 0 or objetivo < 0:
        raise ValueError("El avance y el objetivo no pueden ser negativos.")

    if avance >= objetivo:
        return VERDE
    if avance >= objetivo * FACTOR_NARANJO:
        return NARANJO
    return ROJO


# ============================================================
# FILA POR FUNCIONARIO Y TOTALES DEL EQUIPO
# ============================================================

@dataclass
class FilaEquipo:
    funcionario: object
    cargo: object
    puntaje: Decimal
    ponderacion_total: Decimal
    cantidad_metas: int
    objetivo: Decimal
    semaforo: str
    ultimo_ingreso: object
    dias_sin_ingresar: object
    total_ingresos: int
    ingresos_con_puntaje: int
    promedio_diario: Decimal

    @property
    def tiene_metas(self):
        return self.cantidad_metas > 0

    @property
    def ponderacion_incompleta(self):
        return self.tiene_metas and self.ponderacion_total != CIEN

    @property
    def etiqueta_semaforo(self):
        return ETIQUETAS_SEMAFORO[self.semaforo]


@dataclass
class ResumenEquipo:
    periodo: object
    fecha_referencia: object
    dias_periodo: int
    dias_pasados: int
    objetivo: Decimal
    filas: list = field(default_factory=list)

    @property
    def filas_con_metas(self):
        return [fila for fila in self.filas if fila.tiene_metas]

    @property
    def puntaje_promedio(self):
        """Promedio del equipo (hoja SEMAFORO, fila PROMEDIO); sin metas no cuenta."""
        filas = self.filas_con_metas
        if not filas:
            return Decimal("0.00")
        return redondear(sum(fila.puntaje for fila in filas) / len(filas))

    @property
    def semaforo(self):
        if not self.filas_con_metas:
            return SIN_METAS
        return calcular_semaforo(self.puntaje_promedio, self.objetivo)

    @property
    def etiqueta_semaforo(self):
        return ETIQUETAS_SEMAFORO[self.semaforo]

    @property
    def total_ingresos(self):
        return sum(fila.total_ingresos for fila in self.filas)

    @property
    def ingresos_diarios(self):
        """Ingresos diarios de la delegación (hoja RESUMEN, fila DELEGACION)."""
        return redondear(sum(fila.promedio_diario for fila in self.filas))

    def contar(self, color):
        return sum(1 for fila in self.filas if fila.semaforo == color)

    @property
    def conteo_semaforo(self):
        return [
            {"clave": clave, "nombre": ETIQUETAS_SEMAFORO[clave], "total": self.contar(clave)}
            for clave in (VERDE, NARANJO, ROJO, SIN_METAS)
        ]


def calcular_fila(funcionario, periodo, fecha_referencia, objetivo, dias_ausencia=0):
    matriz = obtener_mi_matriz(funcionario=funcionario, periodo=periodo, dias_ausencia=dias_ausencia)
    ingresos = obtener_resumen_ingresos(
        funcionario=funcionario, periodo=periodo, fecha_referencia=fecha_referencia,
    )

    cantidad_metas = len(matriz["items"])
    # Puntaje final: incluye felicitaciones y reclamos (R8).
    puntaje = matriz["puntaje_final"]

    ultimo = ingresos["ultimo_ingreso"]
    dias_sin_ingresar = None
    if ultimo is not None:
        fecha_ultimo = timezone.localtime(ultimo.fecha_ingreso, ZONA_CHILE).date()
        dias_sin_ingresar = max((fecha_referencia - fecha_ultimo).days, 0)

    return FilaEquipo(
        funcionario=funcionario,
        cargo=funcionario.cargo,
        puntaje=puntaje,
        ponderacion_total=matriz["ponderacion_total"],
        cantidad_metas=cantidad_metas,
        objetivo=objetivo,
        semaforo=calcular_semaforo(puntaje, objetivo) if cantidad_metas else SIN_METAS,
        ultimo_ingreso=ultimo,
        dias_sin_ingresar=dias_sin_ingresar,
        total_ingresos=ingresos["total_ingresos"],
        ingresos_con_puntaje=ingresos["ingresos_con_puntaje"],
        promedio_diario=ingresos["promedio_diario"],
    )


def calcular_resumen_equipo(funcionarios, periodo, fecha_referencia):
    """
    Arma la tabla del equipo, ordenada de mayor a menor puntaje.

    Las ausencias de cada funcionario (R9, registradas por el delegado)
    ajustan su meta, igual que en «Mi matriz».
    """
    dias_periodo = obtener_dias_periodo(periodo)
    dias_pasados = dias_transcurridos(periodo, fecha_referencia)
    objetivo = calcular_objetivo_al_dia(dias_pasados, dias_periodo)

    resumen = ResumenEquipo(
        periodo=periodo,
        fecha_referencia=fecha_referencia,
        dias_periodo=dias_periodo,
        dias_pasados=dias_pasados,
        objetivo=objetivo,
    )

    for funcionario in funcionarios:
        resumen.filas.append(calcular_fila(
            funcionario, periodo, fecha_referencia, objetivo,
            dias_ausencia=dias_ausencia_en_periodo(funcionario, periodo),
        ))

    resumen.filas.sort(
        key=lambda fila: (
            not fila.tiene_metas,
            -fila.puntaje,
            fila.funcionario.usuario.get_full_name().casefold(),
        )
    )
    return resumen
