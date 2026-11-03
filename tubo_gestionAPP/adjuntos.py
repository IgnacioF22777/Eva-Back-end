import os
import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.template.defaultfilters import filesizeformat


# ============================================================
# REGLAS DE LOS ARCHIVOS ADJUNTOS DE UN AVANCE
# ============================================================
# Se acepta cualquier tipo de archivo (fotografías, PDF, planillas,
# documentos, comprimidos, audio o video), con tres límites:
#   - cantidad máxima de archivos por avance,
#   - tamaño máximo por archivo,
#   - tamaño máximo del total de archivos de un avance.
# Se rechazan los ejecutables y scripts porque podrían ejecutarse en el
# equipo de quien descarga la evidencia.
#
# Los límites se pueden ajustar por variable de entorno sin tocar el
# código (ver config/settings.py).

MB = 1024 * 1024

MAX_ARCHIVOS = getattr(settings, "ADJUNTOS_MAX_ARCHIVOS", 5)
MAX_BYTES_POR_ARCHIVO = getattr(settings, "ADJUNTOS_MAX_MB_POR_ARCHIVO", 10) * MB
MAX_BYTES_TOTAL = getattr(settings, "ADJUNTOS_MAX_MB_TOTAL", 25) * MB
MAX_LARGO_NOMBRE = 150

EXTENSIONES_BLOQUEADAS = {
    # Ejecutables e instaladores
    "exe", "msi", "com", "scr", "dll", "bin", "apk", "app", "deb", "rpm",
    # Scripts
    "bat", "cmd", "ps1", "vbs", "vbe", "wsf", "js", "jse", "jar", "sh",
    "py", "php", "phtml", "pl", "cgi", "asp", "aspx", "jsp",
    # Páginas que el navegador podría interpretar
    "htm", "html", "xhtml", "svg",
    # Accesos directos y archivos de registro
    "lnk", "reg", "hta", "cpl",
}


def extension_de(nombre):
    return os.path.splitext(nombre or "")[1].lower().lstrip(".")


def validar_archivo_adjunto(archivo):
    """Valida un archivo individual: nombre, extensión y tamaño."""
    nombre = os.path.basename(getattr(archivo, "name", "") or "")

    if not nombre:
        raise ValidationError("El archivo no tiene nombre.")

    if len(nombre) > MAX_LARGO_NOMBRE:
        raise ValidationError(
            f"El nombre del archivo «{nombre[:40]}…» supera los "
            f"{MAX_LARGO_NOMBRE} caracteres."
        )

    extension = extension_de(nombre)

    if extension in EXTENSIONES_BLOQUEADAS:
        raise ValidationError(
            f"El archivo «{nombre}» no está permitido: los archivos "
            f".{extension} pueden ejecutar código."
        )

    if archivo.size == 0:
        raise ValidationError(f"El archivo «{nombre}» está vacío.")

    if archivo.size > MAX_BYTES_POR_ARCHIVO:
        raise ValidationError(
            f"El archivo «{nombre}» pesa {filesizeformat(archivo.size)} y "
            f"el máximo por archivo es {filesizeformat(MAX_BYTES_POR_ARCHIVO)}."
        )


def validar_conjunto_adjuntos(archivos):
    """Valida la cantidad y el peso total de los archivos de un avance."""
    if len(archivos) > MAX_ARCHIVOS:
        raise ValidationError(
            f"Puede adjuntar como máximo {MAX_ARCHIVOS} archivos por avance."
        )

    total = sum(archivo.size for archivo in archivos)

    if total > MAX_BYTES_TOTAL:
        raise ValidationError(
            f"Los archivos suman {filesizeformat(total)} y el máximo por "
            f"avance es {filesizeformat(MAX_BYTES_TOTAL)}."
        )


def ruta_adjunto(instancia, nombre):
    """
    Guarda el archivo con un nombre aleatorio: evita choques entre
    archivos con el mismo nombre y que el nombre original (que escribe
    el usuario) forme parte de la ruta en el servidor. El nombre
    original se conserva en la base de datos para la descarga.
    """
    extension = extension_de(nombre)
    sufijo = f".{extension}" if extension else ""

    return f"avances/{uuid.uuid4().hex}{sufijo}"
