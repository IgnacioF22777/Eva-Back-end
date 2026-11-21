"""Pruebas de la configuración HTTPS (RNF-06, OWASP A02).

CP-SEG-HTTPS-001 a 004. La configuración se lee al importar settings, así que
cada caso la carga en un proceso aparte con las variables de entorno del caso.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

from django.test import SimpleTestCase

RAIZ = Path(__file__).resolve().parent.parent

LEER_SETTINGS = (
    "import json, config.settings as s;"
    "print(json.dumps({"
    "'use_https': s.USE_HTTPS,"
    "'session_secure': getattr(s, 'SESSION_COOKIE_SECURE', False),"
    "'csrf_secure': getattr(s, 'CSRF_COOKIE_SECURE', False),"
    "'proxy': list(getattr(s, 'SECURE_PROXY_SSL_HEADER', None) or []),"
    "'origins': s.CSRF_TRUSTED_ORIGINS,"
    "'hsts': getattr(s, 'SECURE_HSTS_SECONDS', 0),"
    "'redirect': getattr(s, 'SECURE_SSL_REDIRECT', False)}))"
)



def cargar_settings(**variables):
    # Valores base explícitos: load_dotenv() no pisa variables ya definidas,
    # así un .env de servidor con USE_HTTPS=True no altera el resultado.
    entorno = dict(os.environ)
    entorno.update(
        SECRET_KEY="clave-de-prueba-https",
        USE_HTTPS="False",
        CSRF_TRUSTED_ORIGINS="",
        SECURE_SSL_REDIRECT="False",
        SECURE_HSTS_SECONDS="0",
    )
    entorno.update(variables)
    salida = subprocess.run(
        [sys.executable, "-c", LEER_SETTINGS],
        cwd=RAIZ,
        env=entorno,
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(salida.stdout.strip().splitlines()[-1])


class ConfiguracionHttpsTests(SimpleTestCase):
    def test_sin_variable_queda_http(self):
        """CP-SEG-HTTPS-001: sin USE_HTTPS el entorno local sigue en HTTP."""
        cfg = cargar_settings()
        self.assertFalse(cfg["use_https"])
        self.assertFalse(cfg["session_secure"])
        self.assertFalse(cfg["csrf_secure"])
        self.assertEqual(cfg["proxy"], [])

    def test_con_https_las_cookies_son_seguras(self):
        """CP-SEG-HTTPS-002: con USE_HTTPS=True las cookies solo viajan cifradas."""
        cfg = cargar_settings(USE_HTTPS="True")
        self.assertTrue(cfg["use_https"])
        self.assertTrue(cfg["session_secure"])
        self.assertTrue(cfg["csrf_secure"])
        self.assertEqual(cfg["proxy"], ["HTTP_X_FORWARDED_PROTO", "https"])
        self.assertFalse(cfg["redirect"])
        self.assertEqual(cfg["hsts"], 0)

    def test_origenes_csrf_desde_el_entorno(self):
        """CP-SEG-HTTPS-003: CSRF_TRUSTED_ORIGINS se lee separado por comas."""
        cfg = cargar_settings(
            CSRF_TRUSTED_ORIGINS="https://44-217-180-71.sslip.io, https://otro.cl"
        )
        self.assertEqual(
            cfg["origins"],
            ["https://44-217-180-71.sslip.io", "https://otro.cl"],
        )

    def test_hsts_y_redireccion_opcionales(self):
        """CP-SEG-HTTPS-004: HSTS y redirección se activan solo si se piden."""
        cfg = cargar_settings(
            USE_HTTPS="True", SECURE_HSTS_SECONDS="3600", SECURE_SSL_REDIRECT="True"
        )
        self.assertEqual(cfg["hsts"], 3600)
        self.assertTrue(cfg["redirect"])
