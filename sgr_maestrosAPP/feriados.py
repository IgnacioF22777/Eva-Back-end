from datetime import date, timedelta


# ============================================================
# FERIADOS NACIONALES DE CHILE PARA EL CÁLCULO DE DÍAS COMPUTABLES
# ============================================================
# Se consideran los feriados de fecha fija y los de Semana Santa
# (Viernes y Sábado Santo), que se calculan a partir del Domingo de
# Resurrección. Los feriados que la ley traslada cada año (San Pedro y
# San Pablo, Encuentro de Dos Mundos, Iglesias Evangélicas, Pueblos
# Indígenas) y los feriados regionales no se incluyen: si corresponde,
# el período puede ajustarse con observaciones.

FERIADOS_FIJOS = [
    (1, 1),    # Año Nuevo
    (5, 1),    # Día del Trabajo
    (5, 21),   # Glorias Navales
    (7, 16),   # Virgen del Carmen
    (8, 15),   # Asunción de la Virgen
    (9, 18),   # Independencia Nacional
    (9, 19),   # Glorias del Ejército
    (11, 1),   # Todos los Santos
    (12, 8),   # Inmaculada Concepción
    (12, 25),  # Navidad
]


def domingo_de_resurreccion(anio):
    """Algoritmo de Gauss (calendario gregoriano, versión de Meeus)."""
    a = anio % 19
    b, c = divmod(anio, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    mes, dia = divmod(h + l - 7 * m + 114, 31)

    return date(anio, mes, dia + 1)


def feriados_del_anio(anio):
    pascua = domingo_de_resurreccion(anio)

    feriados = {date(anio, mes, dia) for mes, dia in FERIADOS_FIJOS}
    feriados.add(pascua - timedelta(days=2))  # Viernes Santo
    feriados.add(pascua - timedelta(days=1))  # Sábado Santo

    return feriados


def feriados_entre(fecha_inicio, fecha_fin):
    """Lista de feriados comprendidos en el rango (ambos incluidos)."""
    feriados = set()

    for anio in range(fecha_inicio.year, fecha_fin.year + 1):
        feriados |= feriados_del_anio(anio)

    return sorted(f for f in feriados if fecha_inicio <= f <= fecha_fin)
