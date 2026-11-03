from django.conf import settings
from django.core.cache import cache
from django.core.cache.backends.db import DatabaseCache
from django.core.cache.backends.locmem import LocMemCache
from django.db import connection
from django.test import TestCase
from django.urls import reverse

from .tests import CLAVE, crear_usuario
from .views import MAX_INTENTOS_LOGIN, clave_intentos


def otro_worker():
    """
    Una instancia nueva del backend de caché, como la que tiene cada
    worker de Gunicorn en su propio proceso.
    """
    configuracion = settings.CACHES["default"]
    return DatabaseCache(configuracion["LOCATION"], {})


class PruebasCacheCompartida(TestCase):
    """
    Punto 7: el bloqueo de inicio de sesión debe funcionar igual aunque
    Gunicorn atienda cada intento con un worker (proceso) distinto.
    """

    @classmethod
    def setUpTestData(cls):
        cls.usuario = crear_usuario("12.345.678-5", "funcionario@laserena.cl")

    def setUp(self):
        cache.clear()

    def intento_fallido(self):
        return self.client.post(
            reverse("seguridad:login"),
            {"username": "12.345.678-5", "password": "incorrecta"},
        )

    def test_la_cache_se_guarda_en_la_base_de_datos(self):
        self.assertEqual(
            settings.CACHES["default"]["BACKEND"],
            "django.core.cache.backends.db.DatabaseCache",
        )
        self.assertIn(
            settings.CACHES["default"]["LOCATION"],
            connection.introspection.table_names(),
        )

    def test_los_workers_comparten_el_contador(self):
        for _ in range(3):
            self.intento_fallido()

        # Otro proceso ve los mismos 3 intentos.
        self.assertEqual(otro_worker().get(clave_intentos("12.345.678-5")), 3)

    def test_la_memoria_local_no_se_compartia(self):
        """Documenta el problema anterior: cada worker tenía su contador."""
        worker_a = LocMemCache("worker-a", {})
        worker_b = LocMemCache("worker-b", {})

        worker_a.set("login_intentos:x", 4)
        self.assertIsNone(worker_b.get("login_intentos:x"))

    def test_bloqueo_tras_intentos_repartidos_entre_workers(self):
        # Simula que otros workers ya registraron 4 fallos.
        otro_worker().set(clave_intentos("12.345.678-5"), MAX_INTENTOS_LOGIN - 1, 900)

        # El quinto fallo, atendido por este worker, completa el límite.
        self.intento_fallido()

        respuesta = self.client.post(
            reverse("seguridad:login"),
            {"username": "12.345.678-5", "password": CLAVE},
        )

        # Incluso con la contraseña correcta queda bloqueado.
        self.assertEqual(respuesta.status_code, 429)
        self.assertContains(respuesta, "Demasiados intentos", status_code=429)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_login_correcto_limpia_el_contador_para_todos(self):
        self.intento_fallido()
        self.intento_fallido()

        respuesta = self.client.post(
            reverse("seguridad:login"),
            {"username": "12.345.678-5", "password": CLAVE},
        )
        self.assertEqual(respuesta.status_code, 302)

        self.assertIsNone(otro_worker().get(clave_intentos("12.345.678-5")))
