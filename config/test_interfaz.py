"""Regresiones de interfaz encontradas al ejecutar el protocolo (CM-001 y CM-002).

CP-UI-001 a 004. Se prueban en el código porque el desborde y el contraste se
miden en el navegador: estas pruebas fallan si alguien quita la corrección.
"""

import re
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

PLANTILLAS = Path(settings.BASE_DIR) / "templates"
CSS = Path(settings.BASE_DIR) / "static" / "css" / "custom.css"


class PruebasInterfaz(SimpleTestCase):

    def test_CP_UI_001_tablas_con_scroll_contienen_sus_etiquetas_ocultas(self):
        """CP-UI-001 (CM-001): .table-responsive es posicionado para que las
        etiquetas .visually-hidden no ensanchen la página en el celular
        (tubo de seguimiento y verificación medían 685 y 630 px en 375 px)."""
        css = CSS.read_text(encoding="utf-8")
        self.assertRegex(css, r"\.table-responsive\s*\{[^}]*position:\s*relative")

    def test_CP_UI_002_etiquetas_del_grafico_semanal_se_encogen(self):
        """CP-UI-002 (CM-001): las etiquetas de semana del dashboard pueden
        encogerse (antes medían 457 px en una pantalla de 375 px)."""
        html = (PLANTILLAS / "puntaje_equipo" / "dashboard.html").read_text(encoding="utf-8")
        self.assertIn("graf-etiquetas", html)
        self.assertRegex(html, r"\.graf-etiquetas\s*>\s*div\s*\{[^}]*min-width:\s*0")

    def test_CP_UI_003_sin_texto_amarillo_de_bajo_contraste(self):
        """CP-UI-003 (CM-002): ningún texto usa text-warning (#FFC107 sobre
        blanco = 1,63:1, bajo el mínimo WCAG de 3:1 para texto grande);
        se usa text-warning-emphasis (#664D03)."""
        patron = re.compile(r'class="[^"]*\btext-warning(?![-\w])')
        con_falla = [
            str(ruta.relative_to(PLANTILLAS))
            for ruta in PLANTILLAS.rglob("*.html")
            if patron.search(ruta.read_text(encoding="utf-8"))
        ]
        self.assertEqual(con_falla, [])

    def test_CP_UI_004_contraste_del_amarillo_enfatizado(self):
        """CP-UI-004 (CM-002): #664D03 sobre blanco cumple 4,5:1."""
        def luminancia(hexa):
            canales = [int(hexa[i:i + 2], 16) / 255 for i in (0, 2, 4)]
            lineal = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in canales]
            return 0.2126 * lineal[0] + 0.7152 * lineal[1] + 0.0722 * lineal[2]

        razon = (1 + 0.05) / (luminancia("664d03") + 0.05)
        self.assertGreaterEqual(razon, 4.5)
