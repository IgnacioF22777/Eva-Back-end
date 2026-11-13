"""
Importación del registro de juntas de vecinos y organizaciones
comunitarias desde la planilla municipal (.xlsx).

La planilla llega «sin verificar»: fechas como número serial de Excel o
«S/Inf.», socios con texto («6 CLUBES»), números de registro repetidos y
territorios abreviados. La importación nunca se detiene por una fila: la
carga con lo que se pueda interpretar y deja la advertencia en las
observaciones de la organización y en el resumen.
"""
import re
import zipfile
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, timedelta
from xml.etree import ElementTree

from django.core.exceptions import ValidationError
from django.db import transaction

from delegacionesAPP.models import Delegacion

from .models import OrganizacionComunitaria, normalizar, tipo_por_nombre


NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
NS_REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"

# Columnas esperadas (encabezados del registro municipal, normalizados).
COLUMNAS = {
    "nombre": "ORGANIZACIONES",
    "domicilio": "DOMICILIO LEGAL",
    "territorio": "TERRIT. DELEG.",
    "socios": "SOCIOS ACTIVOS",
    "fecha_constitucion": "FECHA CONSTIT.",
    "numero_registro": "Nº REG. P.J.",
    "fecha_inscripcion": "FECHA INSCRIPC EN REG.",
    "registro_directiva": "REG. DIR. Nº",
}

# Territorio de la planilla -> palabra que identifica a la delegación.
TERRITORIOS = {
    "CENTRO": "CENTRO",
    "CIAS": "COMPANIAS",
    "COMPANIAS": "COMPANIAS",
    "PAMPA": "PAMPA",
    "RURAL": "RURAL",
    "ANTENA": "ANTENA",
    "AV DEL MAR": "DEL MAR",
    "AVENIDA DEL MAR": "DEL MAR",
}

EXCEL_EPOCA = date(1899, 12, 30)
FECHA_MINIMA = date(1900, 1, 2)


class ArchivoInvalido(Exception):
    pass


# ------------------------------------------------------------------ lector
def leer_xlsx(ruta):
    """Devuelve (encabezados, filas) de la primera hoja; filas como dict."""
    try:
        libro = zipfile.ZipFile(ruta)
    except (zipfile.BadZipFile, FileNotFoundError, IsADirectoryError) as error:
        raise ArchivoInvalido(f"No se pudo abrir {ruta} como planilla .xlsx ({error}).")

    with libro:
        nombres = libro.namelist()
        compartidos = []
        if "xl/sharedStrings.xml" in nombres:
            raiz = ElementTree.fromstring(libro.read("xl/sharedStrings.xml"))
            compartidos = ["".join(t.text or "" for t in si.iter(NS + "t"))
                           for si in raiz.findall(NS + "si")]

        try:
            libro_xml = ElementTree.fromstring(libro.read("xl/workbook.xml"))
            relaciones = ElementTree.fromstring(libro.read("xl/_rels/workbook.xml.rels"))
        except KeyError:
            raise ArchivoInvalido(f"{ruta} no tiene la estructura de una planilla .xlsx.")

        destinos = {r.get("Id"): r.get("Target") for r in relaciones}
        primera = next(libro_xml.iter(NS + "sheet"))
        ruta_hoja = destinos[primera.get(NS_REL + "id")].lstrip("/")
        if not ruta_hoja.startswith("xl/"):
            ruta_hoja = "xl/" + ruta_hoja
        hoja = ElementTree.fromstring(libro.read(ruta_hoja))

    filas = []
    for fila in hoja.iter(NS + "row"):
        valores = {}
        for celda in fila.findall(NS + "c"):
            columna = re.match(r"[A-Z]+", celda.get("r")).group()
            tipo = celda.get("t")
            if tipo == "inlineStr":
                valor = "".join(t.text or "" for t in celda.iter(NS + "t"))
            else:
                v = celda.find(NS + "v")
                if v is None:
                    continue
                valor = compartidos[int(v.text)] if tipo == "s" else v.text
            valores[columna] = valor
        filas.append((int(fila.get("r")), valores))

    if not filas:
        raise ArchivoInvalido("La planilla está vacía.")

    _, cabecera = filas[0]
    encabezados = {normalizar(texto): col for col, texto in cabecera.items()}
    faltantes = [t for t in COLUMNAS.values() if normalizar(t) not in encabezados]
    if faltantes:
        raise ArchivoInvalido("Faltan columnas en la planilla: " + ", ".join(faltantes))

    columna_de = {campo: encabezados[normalizar(t)] for campo, t in COLUMNAS.items()}
    datos = []
    for numero, valores in filas[1:]:
        registro = {campo: str(valores.get(col, "")).strip() for campo, col in columna_de.items()}
        if any(registro.values()):
            datos.append((numero, registro))
    return datos


# ------------------------------------------------------------------ limpieza
def texto_entero(valor):
    """'4006.0' -> '4006'; deja intacto el texto ('352-BIS')."""
    valor = " ".join(str(valor or "").split())
    return valor[:-2] if re.fullmatch(r"\d+\.0", valor) else valor


def fecha_excel(valor):
    """Número serial de Excel -> date. Devuelve (fecha, advertencia)."""
    valor = str(valor or "").strip()
    if not valor:
        return None, None
    if not re.fullmatch(r"\d+(\.\d+)?", valor):
        return None, f"fecha «{valor}» sin información"
    fecha = EXCEL_EPOCA + timedelta(days=int(float(valor)))
    if fecha < FECHA_MINIMA:
        return None, "fecha vacía en el registro"
    return fecha, None


def entero_socios(valor):
    valor = str(valor or "").strip()
    if not valor:
        return None, None
    if re.fullmatch(r"\d+(\.0)?", valor):
        return int(float(valor)), None
    numero = re.match(r"\d+", valor)
    if numero:
        return int(numero.group()), f"socios «{valor}» interpretado como {numero.group()}"
    return None, f"socios «{valor}» no es un número"


def delegaciones_por_territorio():
    mapa = {}
    delegaciones = list(Delegacion.objects.all())
    for territorio, palabra in TERRITORIOS.items():
        candidatas = [d for d in delegaciones if palabra in normalizar(d.nombre)]
        activas = [d for d in candidatas if d.activo]
        if activas or candidatas:
            mapa[territorio] = (activas or candidatas)[0]
    return mapa


# ------------------------------------------------------------------ carga
@dataclass
class Resumen:
    leidas: int = 0
    creadas: int = 0
    actualizadas: int = 0
    sin_cambios: int = 0
    protegidas: int = 0
    omitidas: list = field(default_factory=list)
    advertencias: Counter = field(default_factory=Counter)
    ejemplos: dict = field(default_factory=dict)

    def avisar(self, tipo, ejemplo):
        self.advertencias[tipo] += 1
        self.ejemplos.setdefault(tipo, ejemplo)


CAMPOS_DE_ORIGEN = (
    "domicilio", "delegacion_id", "territorio_origen", "socios_activos",
    "fecha_constitucion", "fecha_inscripcion", "registro_directiva",
)


def importar(filas, simular=False):
    """
    Carga las filas leídas. Idempotente: la clave es número de registro +
    nombre normalizado. Las organizaciones ya verificadas no se modifican y
    el tipo solo se asigna al crear (el funcionario puede corregirlo).
    """
    resumen = Resumen(leidas=len(filas))
    mapa = delegaciones_por_territorio()
    hoy = date.today()

    registros_en_archivo = Counter(texto_entero(f["numero_registro"]) for _, f in filas)

    with transaction.atomic():
        existentes = {}
        for org in OrganizacionComunitaria.objects.all():
            existentes[(org.numero_registro.upper(), normalizar(org.nombre))] = org

        for numero_fila, fila in filas:
            nombre = " ".join(fila["nombre"].split())
            registro = texto_entero(fila["numero_registro"])

            if not nombre or not registro:
                resumen.omitidas.append(
                    f"fila {numero_fila}: falta el nombre o el número de registro"
                )
                continue

            avisos = []
            territorio = normalizar(fila["territorio"])
            delegacion = mapa.get(territorio)
            if not territorio:
                avisos.append("sin territorio en el registro")
                resumen.avisar("territorio vacío", nombre)
            elif delegacion is None:
                avisos.append(f"territorio «{fila['territorio']}» sin delegación asociada")
                resumen.avisar(f"territorio {territorio} sin delegación", nombre)

            socios, aviso = entero_socios(fila["socios"])
            if aviso:
                avisos.append(aviso)
                resumen.avisar("socios no numéricos", nombre)

            constitucion, aviso = fecha_excel(fila["fecha_constitucion"])
            if aviso:
                avisos.append("constitución: " + aviso)
                resumen.avisar("fecha de constitución sin información", nombre)

            inscripcion, aviso = fecha_excel(fila["fecha_inscripcion"])
            if aviso:
                avisos.append("inscripción: " + aviso)
                resumen.avisar("fecha de inscripción sin información", nombre)

            if constitucion and inscripcion and inscripcion < constitucion:
                avisos.append("la inscripción es anterior a la constitución")
                resumen.avisar("inscripción anterior a la constitución", nombre)

            for fecha in (constitucion, inscripcion):
                if fecha and fecha > hoy:
                    avisos.append(f"fecha futura ({fecha:%d-%m-%Y})")
                    resumen.avisar("fecha futura", nombre)

            if registros_en_archivo[registro] > 1:
                avisos.append(f"el N° de registro {registro} se repite en el archivo")
                resumen.avisar("número de registro repetido", f"{registro} · {nombre}")

            valores = {
                "domicilio": " ".join(fila["domicilio"].split())[:255],
                "delegacion_id": delegacion.pk if delegacion else None,
                "territorio_origen": fila["territorio"][:50],
                "socios_activos": socios,
                "fecha_constitucion": constitucion,
                "fecha_inscripcion": inscripcion,
                "registro_directiva": texto_entero(fila["registro_directiva"])[:20],
            }
            observacion = (
                "Importado del registro municipal (sin verificar). "
                + ("Advertencias: " + "; ".join(avisos) + "." if avisos else "")
            ).strip()[:1000]

            clave = (registro.upper(), normalizar(nombre))
            org = existentes.get(clave)

            if org is not None and org.verificada:
                resumen.protegidas += 1
                continue

            if org is None:
                org = OrganizacionComunitaria(
                    nombre=nombre[:255],
                    numero_registro=registro[:20],
                    tipo=tipo_por_nombre(nombre),
                    **valores,
                    observaciones=observacion,
                )
                try:
                    org.full_clean()
                except ValidationError as error:
                    resumen.omitidas.append(
                        f"fila {numero_fila} ({nombre}): " + "; ".join(error.messages)
                    )
                    continue
                org.save()
                existentes[clave] = org
                resumen.creadas += 1
                continue

            if all(getattr(org, k) == v for k, v in valores.items()):
                resumen.sin_cambios += 1
                continue

            for campo, valor in valores.items():
                setattr(org, campo, valor)
            org.observaciones = observacion
            org.save()
            resumen.actualizadas += 1

        if simular:
            transaction.set_rollback(True)

    return resumen
