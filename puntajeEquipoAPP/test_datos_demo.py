"""Prueba del comando cargar_datos_demo (CP-DEM-001 a CP-DEM-003)."""

import shutil
import tempfile
from datetime import datetime
from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from actividadesAPP.models import ZONA_CHILE, RegistroActividad
from matrizAPP.models import AjusteDesempeno, Ausencia
from oficinaPartesAPP.models import CartaOficinaPartes
from seguridadAPP.models import PerfilUsuario
from seguridadAPP.roles import sincronizar_roles

User = get_user_model()
CARPETA = tempfile.mkdtemp(prefix="sgr_demo_")
HOY = datetime(2026, 11, 20, 12, 0, tzinfo=ZONA_CHILE)


@override_settings(MEDIA_ROOT=CARPETA)
class PruebasDatosDemo(TestCase):

    @classmethod
    def setUpTestData(cls):
        sincronizar_roles()
        call_command("import_data", stdout=StringIO())
        User.objects.create_superuser("admin", "admin@laserena.cl", "Clave-Admin-2026")

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(CARPETA, ignore_errors=True)

    def setUp(self):
        reloj = patch("django.utils.timezone.now", return_value=HOY)
        reloj.start()
        self.addCleanup(reloj.stop)

    def cargar(self, *args):
        call_command("cargar_datos_demo", "--clave", "Demo-Clave-Larga-2026", *args, stdout=StringIO())

    def test_CP_DEM_001_carga_completa(self):
        """CP-DEM-001: crea equipos, actividades verificadas, tubo, ausencias, ajustes y cartas."""
        self.cargar()
        registros = RegistroActividad.objects.all()
        self.assertGreater(registros.count(), 200)
        self.assertFalse(registros.filter(codigo__isnull=True).exists())
        estados = set(registros.values_list("estado_verificacion", flat=True))
        self.assertEqual(estados, {"APROBADA", "PENDIENTE", "RECHAZADA", "ANTECEDENTES"})
        self.assertTrue(registros.filter(ingresa_tubo=True, estado_tubo="SOLUCIONADO").exists())
        self.assertEqual(Ausencia.objects.count(), 3)
        self.assertEqual(AjusteDesempeno.objects.count(), 3)
        self.assertGreaterEqual(CartaOficinaPartes.objects.count(), 20)

        # Nunca más de 7 ingresos por funcionario y día (R3).
        from django.db.models import Count
        maximo = registros.values("funcionario", "fecha_actividad").annotate(n=Count("id"))
        self.assertLessEqual(max(f["n"] for f in maximo), 7)

        # La funcionaria nueva queda con contraseña temporal.
        self.assertTrue(PerfilUsuario.objects.get(usuario__username="javiera.olivares").debe_cambiar_password)

    def test_CP_DEM_002_idempotente(self):
        """CP-DEM-002: correrlo dos veces no duplica; --reiniciar regenera lo mismo."""
        self.cargar()
        total = RegistroActividad.objects.count()
        self.cargar()
        self.assertEqual(RegistroActividad.objects.count(), total)
        self.cargar("--reiniciar")
        self.assertEqual(Ausencia.objects.count(), 3)
        self.assertGreater(RegistroActividad.objects.count(), 200)

    def test_CP_DEM_004_requisitos_con_mensaje_claro(self):
        """CP-DEM-004 (borde): sin superusuario, o sin las delegaciones de import_data, falla con un mensaje claro y sin crear nada."""
        User.objects.filter(is_superuser=True).update(is_active=False)
        with self.assertRaisesMessage(CommandError, "createsuperuser"):
            self.cargar()
        self.assertFalse(User.objects.filter(email__endswith="@demo.laserena.cl").exists())

        User.objects.filter(is_superuser=True).update(is_active=True)
        from delegacionesAPP.models import Delegacion
        Delegacion.objects.filter(nombre="Delegación Las Compañías").update(nombre="Otra delegación")
        with self.assertRaisesMessage(CommandError, "import_data"):
            self.cargar()
        self.assertFalse(RegistroActividad.objects.exists())

    def test_CP_DEM_003_exige_clave(self):
        """CP-DEM-003 (seguridad): sin --clave no crea cuentas."""
        with self.assertRaises(CommandError):
            call_command("cargar_datos_demo", stdout=StringIO())
        self.assertFalse(User.objects.filter(email__endswith="@demo.laserena.cl").exists())
