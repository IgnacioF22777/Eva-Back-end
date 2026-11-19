"""
Exportación de listados del SGR a Excel (openpyxl) y PDF (ReportLab).

Utilidades compartidas por todas las apps: cada vista de exportación solo
arma los encabezados y las filas (con los mismos filtros, permisos y ámbito
por delegación que su listado) y llama a `exportar_excel` o `exportar_pdf`.

- Excel: título, institución y fecha, encabezados con estilo, filtros
  automáticos y fila de encabezados fija.
- PDF: encabezado con institución y fecha, logo municipal, título, tabla con
  estilo y pie de página con «Página X de Y» (clase NumberedCanvas).
"""

import logging
import os
from datetime import date, datetime
from decimal import Decimal
from xml.sax.saxutils import escape

from django.conf import settings
from django.http import HttpResponse
from django.utils import timezone

# Importaciones necesarias para la exportación a Excel
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

# Importaciones necesarias para la exportación a PDF
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    Image,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


logger = logging.getLogger(__name__)

INSTITUCION = "Ilustre Municipalidad de La Serena"
SISTEMA = "Sistema de Gestión de Resultados (SGR)"
AZUL_SGR = "#1f4788"
GRIS_FILA = "#f0f0f0"

CONTENT_TYPE_EXCEL = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)
CONTENT_TYPE_PDF = "application/pdf"

# Excel no admite nombres de hoja de más de 31 caracteres ni estos símbolos.
CARACTERES_INVALIDOS_HOJA = '[]:*?/\\'

SIN_REGISTROS = "Sin registros para los filtros seleccionados."


# ============================================================
# UTILIDADES COMUNES
# ============================================================

def fecha_generacion():
    """Fecha y hora local (America/Santiago) en que se genera el reporte."""
    return timezone.localtime()


def nombre_archivo(base, extension):
    """Ej.: catalogo_actividades_20261117_0930.xlsx"""
    return f"{base}_{fecha_generacion():%Y%m%d_%H%M}.{extension}"


def nombre_usuario(usuario):
    """Nombre visible de quien genera el reporte (para el encabezado)."""
    if usuario is None or not usuario.is_authenticated:
        return ""
    return usuario.get_full_name() or usuario.get_username()


def si_no(valor):
    return "Sí" if valor else "No"


def activo_inactivo(valor):
    return "Activo" if valor else "Inactivo"


def _normalizar(valor):
    """
    Deja el valor listo para escribirlo en una celda: las fechas con zona
    horaria se pasan a la hora local (Excel no admite zonas horarias) y
    None queda como texto vacío.
    """
    if valor is None:
        return ""
    if isinstance(valor, datetime) and timezone.is_aware(valor):
        return timezone.localtime(valor).replace(tzinfo=None)
    return valor


def a_texto(valor):
    """Representación de un valor para el PDF."""
    valor = _normalizar(valor)
    if isinstance(valor, datetime):
        return valor.strftime("%d/%m/%Y %H:%M")
    if isinstance(valor, date):
        return valor.strftime("%d/%m/%Y")
    if isinstance(valor, Decimal):
        # 25.00 -> "25"; 33.33 -> "33,33"
        texto = format(valor.normalize(), "f")
        return texto.replace(".", ",")
    return str(valor)


def _respuesta(content_type, archivo):
    response = HttpResponse(content_type=content_type)
    # Se establece el encabezado de la respuesta para indicar que es un
    # archivo adjunto.
    response["Content-Disposition"] = f'attachment; filename="{archivo}"'
    return response


# ============================================================
# 1. EXPORTAR A EXCEL (openpyxl)
# ============================================================

def exportar_excel(titulo, encabezados, filas, archivo, usuario=None):
    """
    Devuelve un HttpResponse con un libro .xlsx.

    titulo:      título del reporte y nombre de la hoja.
    encabezados: lista con el nombre de cada columna.
    filas:       lista de listas con los valores (texto, números o fechas).
    archivo:     nombre base del archivo, sin extensión.
    """
    total_columnas = len(encabezados)
    ultima_columna = get_column_letter(total_columnas)

    # Creamos un libro de trabajo de Excel y seleccionamos la hoja activa
    wb = Workbook()
    ws = wb.active
    nombre_hoja = "".join(
        c for c in titulo if c not in CARACTERES_INVALIDOS_HOJA
    )
    ws.title = nombre_hoja[:31] or "Reporte"

    # Fila 1: título del reporte (celdas combinadas, fondo azul)
    ws.merge_cells(f"A1:{ultima_columna}1")
    celda_titulo = ws["A1"]
    celda_titulo.value = titulo
    celda_titulo.font = Font(bold=True, size=14, color="FFFFFF")
    celda_titulo.fill = PatternFill("solid", fgColor=AZUL_SGR[1:])
    celda_titulo.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[1].height = 24

    # Fila 2: institución, fecha y usuario que genera el reporte
    detalle = (
        f"{INSTITUCION} - {SISTEMA} | "
        f"Generado el {fecha_generacion():%d/%m/%Y %H:%M}"
    )
    quien = nombre_usuario(usuario)
    if quien:
        detalle += f" por {quien}"
    ws.merge_cells(f"A2:{ultima_columna}2")
    ws["A2"].value = detalle
    ws["A2"].font = Font(italic=True, size=9, color="555555")
    ws["A2"].alignment = Alignment(horizontal="center")

    # Fila 4: encabezados de las columnas
    fila_encabezados = 4
    borde = Side(style="thin", color="BFBFBF")
    for columna, nombre in enumerate(encabezados, start=1):
        celda = ws.cell(row=fila_encabezados, column=columna, value=nombre)
        celda.font = Font(bold=True, color="FFFFFF")
        celda.fill = PatternFill("solid", fgColor="343A40")
        celda.alignment = Alignment(
            horizontal="center", vertical="center", wrap_text=True
        )
        celda.border = Border(top=borde, bottom=borde, left=borde, right=borde)

    # Escribimos los datos
    anchos = [len(str(nombre)) for nombre in encabezados]
    for numero, fila in enumerate(filas, start=fila_encabezados + 1):
        for columna, valor in enumerate(fila, start=1):
            valor = _normalizar(valor)
            celda = ws.cell(row=numero, column=columna, value=valor)

            if isinstance(valor, str):
                # Un texto que comienza con "=" se guarda como texto y no
                # como fórmula (evita la inyección de fórmulas en Excel).
                celda.data_type = "s"
                celda.alignment = Alignment(vertical="top", wrap_text=True)
            elif isinstance(valor, datetime):
                celda.number_format = "DD/MM/YYYY HH:MM"
            elif isinstance(valor, date):
                celda.number_format = "DD/MM/YYYY"

            celda.border = Border(
                top=borde, bottom=borde, left=borde, right=borde
            )
            anchos[columna - 1] = max(
                anchos[columna - 1], len(a_texto(valor))
            )

    if not filas:
        ws.cell(row=fila_encabezados + 1, column=1, value=SIN_REGISTROS)

    # Ancho de columnas según el contenido (con un máximo razonable)
    for columna, ancho in enumerate(anchos, start=1):
        ws.column_dimensions[get_column_letter(columna)].width = min(
            max(ancho + 2, 10), 50
        )

    # Encabezados fijos al desplazarse y filtros automáticos
    ws.freeze_panes = ws.cell(row=fila_encabezados + 1, column=1)
    if filas:
        ws.auto_filter.ref = (
            f"A{fila_encabezados}:{ultima_columna}"
            f"{fila_encabezados + len(filas)}"
        )

    # Devolvemos el archivo Excel como respuesta
    response = _respuesta(CONTENT_TYPE_EXCEL, nombre_archivo(archivo, "xlsx"))
    # Guardamos el libro de trabajo en la respuesta
    wb.save(response)
    return response


# ============================================================
# 2. EXPORTAR A PDF (ReportLab)
# ============================================================

class NumberedCanvas(canvas.Canvas):
    """
    Lienzo personalizado que agrega el pie de página con «Página X de Y».

    Para conocer el total de páginas, cada página se guarda en memoria y el
    pie se dibuja recién en save(), cuando el documento ya está completo.
    """

    def __init__(self, *args, **kwargs):
        canvas.Canvas.__init__(self, *args, **kwargs)
        self._paginas_guardadas = []

    def showPage(self):
        # Guardamos el estado de la página en lugar de emitirla todavía
        self._paginas_guardadas.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total_paginas = len(self._paginas_guardadas)
        for estado in self._paginas_guardadas:
            self.__dict__.update(estado)
            self._draw_footer(total_paginas)
            canvas.Canvas.showPage(self)
        canvas.Canvas.save(self)

    def _draw_footer(self, total_paginas):
        """Dibuja el pie de página en la página actual del PDF."""
        ancho = self._pagesize[0]
        # Guardamos el estado actual del lienzo
        self.saveState()
        # Línea horizontal en la parte inferior de la página
        self.setStrokeColor(colors.HexColor(AZUL_SGR))
        self.setLineWidth(1)
        self.line(0.5 * inch, 0.6 * inch, ancho - 0.5 * inch, 0.6 * inch)
        # Número de página y copyright
        self.setFont("Helvetica", 8)
        self.setFillColor(colors.black)
        self.drawString(
            0.5 * inch,
            0.4 * inch,
            f"Página {self._pageNumber} de {total_paginas}",
        )
        self.drawRightString(
            ancho - 0.5 * inch,
            0.4 * inch,
            f"© {fecha_generacion().year} - {INSTITUCION}",
        )
        # Restauramos el estado del lienzo para no afectar otros elementos
        self.restoreState()


def _ruta_logo():
    return os.path.join(settings.BASE_DIR, "static", "images", "logo_reportes.png")


def exportar_pdf(
    titulo,
    encabezados,
    filas,
    archivo,
    usuario=None,
    anchos=None,
    horizontal=False,
    filtros=None,
):
    """
    Devuelve un HttpResponse con el reporte en PDF.

    anchos:     proporción de ancho de cada columna (ej. [1, 3, 2]); por
                defecto todas iguales.
    horizontal: página carta horizontal para tablas con muchas columnas.
    filtros:    texto con los filtros aplicados, para dejarlos registrados.
    """
    # Creamos la respuesta HTTP con el tipo de contenido PDF
    response = _respuesta(CONTENT_TYPE_PDF, nombre_archivo(archivo, "pdf"))

    tamano = landscape(letter) if horizontal else letter

    # Tamaño de la página carta con márgenes
    doc = SimpleDocTemplate(
        response,
        pagesize=tamano,
        rightMargin=0.5 * inch,
        leftMargin=0.5 * inch,
        topMargin=0.5 * inch,
        bottomMargin=0.8 * inch,
        title=titulo,
        author=INSTITUCION,
    )

    # Lista para almacenar los elementos del PDF
    elementos = []

    # Estilos de muestra de ReportLab y estilos propios
    styles = getSampleStyleSheet()

    header_style = ParagraphStyle(
        "HeaderCustom",
        parent=styles["Normal"],
        fontSize=11,
        fontName="Helvetica-Bold",
        textColor=colors.HexColor(AZUL_SGR),
        spaceAfter=0.1 * inch,
    )
    header_info_style = ParagraphStyle(
        "HeaderInfo",
        parent=styles["Normal"],
        fontSize=9,
        fontName="Helvetica",
        textColor=colors.black,
        spaceAfter=0.05 * inch,
    )
    titulo_style = ParagraphStyle(
        "TituloCustom",
        parent=styles["Heading1"],
        fontSize=20,
        textColor=colors.HexColor(AZUL_SGR),
        spaceAfter=0.2 * inch,
        alignment=TA_CENTER,
        fontName="Helvetica-Bold",
    )
    celda_encabezado_style = ParagraphStyle(
        "CeldaEncabezado",
        parent=styles["Normal"],
        fontSize=9,
        leading=11,
        fontName="Helvetica-Bold",
        textColor=colors.whitesmoke,
        alignment=TA_CENTER,
    )
    celda_style = ParagraphStyle(
        "Celda",
        parent=styles["Normal"],
        fontSize=8,
        leading=10,
        fontName="Helvetica",
    )

    # Encabezado: institución, sistema, fecha y usuario
    elementos.append(Paragraph(f"REPORTE: {escape(titulo.upper())}", header_style))
    elementos.append(Paragraph(f"Institución: {INSTITUCION}", header_info_style))
    elementos.append(Paragraph(f"Sistema: {SISTEMA}", header_info_style))
    elementos.append(
        Paragraph(
            f"Fecha: {fecha_generacion():%d/%m/%Y %H:%M}", header_info_style
        )
    )
    quien = nombre_usuario(usuario)
    if quien:
        elementos.append(
            Paragraph(f"Generado por: {escape(quien)}", header_info_style)
        )
    if filtros:
        elementos.append(
            Paragraph(f"Filtros: {escape(filtros)}", header_info_style)
        )
    elementos.append(Spacer(1, 0.15 * inch))

    # Logo municipal (si existe)
    try:
        logo_path = _ruta_logo()
        if os.path.exists(logo_path):
            logo = Image(logo_path, width=0.9 * inch, height=0.82 * inch)
            elementos.append(logo)
            elementos.append(Spacer(1, 0.1 * inch))
    except Exception as e:  # el reporte se genera igual sin logo
        logger.warning(f"No se pudo cargar el logo: {e}")

    # Título
    elementos.append(Paragraph(escape(titulo), titulo_style))
    elementos.append(Spacer(1, 0.1 * inch))

    # Datos de la tabla: cada celda es un Paragraph para que el texto largo
    # haga salto de línea dentro de la columna. Se escapa el contenido para
    # que caracteres como "<" o "&" no se interpreten como etiquetas.
    datos = [
        [Paragraph(escape(str(nombre)), celda_encabezado_style)
         for nombre in encabezados]
    ]
    for fila in filas:
        datos.append(
            [Paragraph(escape(a_texto(valor)), celda_style) for valor in fila]
        )

    if not filas:
        datos.append(
            [Paragraph(SIN_REGISTROS, celda_style)]
            + [""] * (len(encabezados) - 1)
        )

    # Anchos de columna proporcionales al ancho útil de la página
    ancho_util = tamano[0] - doc.leftMargin - doc.rightMargin
    proporciones = anchos or [1] * len(encabezados)
    total = float(sum(proporciones))
    col_widths = [ancho_util * p / total for p in proporciones]

    # Creamos la tabla; el encabezado se repite en cada página
    tabla = Table(datos, colWidths=col_widths, repeatRows=1)

    estilo = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(AZUL_SGR)),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
        ("TOPPADDING", (0, 0), (-1, 0), 6),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1),
         [colors.white, colors.HexColor(GRIS_FILA)]),
    ]
    if not filas:
        estilo.append(("SPAN", (0, 1), (-1, 1)))
    tabla.setStyle(TableStyle(estilo))

    elementos.append(tabla)

    elementos.append(Spacer(1, 0.15 * inch))
    elementos.append(
        Paragraph(f"Total de registros: {len(filas)}", header_info_style)
    )

    # Construimos el documento PDF con pie de página personalizado
    doc.build(elementos, canvasmaker=NumberedCanvas)
    return response
