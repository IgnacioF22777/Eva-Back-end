"""Pruebas Eva 3: contraseña temporal y cambio obligatorio en el primer ingreso.

CP-PWD-001 a CP-PWD-006 se registran en la matriz de pruebas del informe.
"""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse

from delegacionesAPP.models import Delegacion
from seguridadAPP.models import PerfilUsuario
from seguridadAPP.roles import sincronizar_roles

User = get_user_model()

CLAVE_TEMPORAL = "Temporal-SGR-2026"
CLAVE_NUEVA = "MiClave-Personal-2026"


class PruebasPasswordTemporal(TestCase):

    @classmethod
    def setUpTestData(cls):
        sincronizar_roles()
        cls.centro = Delegacion.objects.create(
            nombre="Centro", direccion="Calle 1", encargado="Delegada",
            email="centro@laserena.cl", telefono="512111111", celular="911111111",
        )
        cls.admin = User.objects.create_superuser("admin", "admin@laserena.cl", "Clave-Admin-2026")

    def crear_por_formulario(self):
        """El administrador registra un usuario desde el mantenedor."""
        self.client.force_login(self.admin)
        respuesta = self.client.post(reverse("seguridad:usuario_crear"), {
            "rut": "12.345.678-5",
            "first_name": "Ana",
            "last_name": "Pérez",
            "email": "ana.perez@laserena.cl",
            "groups": [Group.objects.get(name="Administrativo").pk],
            "delegacion": self.centro.pk,
            "password1": CLAVE_TEMPORAL,
            "password2": CLAVE_TEMPORAL,
            "is_active": "on",
        })
        self.assertRedirects(respuesta, reverse("seguridad:usuario_lista"))
        self.client.logout()
        return User.objects.get(username="12345678-5")

    def test_CP_PWD_001_usuario_nuevo_con_clave_temporal(self):
        """CP-PWD-001: el usuario creado por el administrador queda con contraseña temporal."""
        usuario = self.crear_por_formulario()
        self.assertTrue(usuario.perfil.debe_cambiar_password)

    def test_CP_PWD_002_primer_ingreso_redirige_al_cambio(self):
        """CP-PWD-002: con clave temporal, cualquier página lleva al cambio obligatorio."""
        usuario = self.crear_por_formulario()
        self.client.login(username=usuario.username, password=CLAVE_TEMPORAL)
        for ruta in (reverse("inicio"), reverse("actividades:lista"), reverse("actividades:tubo")):
            with self.subTest(ruta=ruta):
                self.assertRedirects(
                    self.client.get(ruta), reverse("seguridad:cambiar_password"),
                    fetch_redirect_response=False,
                )
        self.assertContains(self.client.get(reverse("seguridad:cambiar_password")), "Primer ingreso")

    def test_CP_PWD_003_cambio_exitoso_libera_el_acceso(self):
        """CP-PWD-003: tras cambiarla, la marca se borra y el sistema queda disponible."""
        usuario = self.crear_por_formulario()
        self.client.login(username=usuario.username, password=CLAVE_TEMPORAL)
        respuesta = self.client.post(reverse("seguridad:cambiar_password"), {
            "old_password": CLAVE_TEMPORAL,
            "new_password1": CLAVE_NUEVA,
            "new_password2": CLAVE_NUEVA,
        })
        self.assertRedirects(respuesta, reverse("inicio"), fetch_redirect_response=False)
        usuario.refresh_from_db()
        self.assertFalse(usuario.perfil.debe_cambiar_password)
        self.assertTrue(usuario.check_password(CLAVE_NUEVA))
        # La sesión sigue activa después del cambio.
        self.assertEqual(self.client.get(reverse("inicio")).status_code, 200)

    def test_CP_PWD_004_clave_temporal_incorrecta_o_debil(self):
        """CP-PWD-004 (borde): clave actual errónea o nueva débil no se aceptan."""
        usuario = self.crear_por_formulario()
        self.client.login(username=usuario.username, password=CLAVE_TEMPORAL)
        for datos in (
            {"old_password": "otra", "new_password1": CLAVE_NUEVA, "new_password2": CLAVE_NUEVA},
            {"old_password": CLAVE_TEMPORAL, "new_password1": "123", "new_password2": "123"},
            {"old_password": CLAVE_TEMPORAL, "new_password1": CLAVE_NUEVA, "new_password2": "distinta-2026"},
        ):
            with self.subTest(datos=datos):
                respuesta = self.client.post(reverse("seguridad:cambiar_password"), datos)
                self.assertEqual(respuesta.status_code, 200)
        usuario.refresh_from_db()
        self.assertTrue(usuario.perfil.debe_cambiar_password)

    def test_CP_PWD_005_restablecer_vuelve_a_ser_temporal(self):
        """CP-PWD-005: si el administrador restablece la clave, vuelve a ser temporal."""
        usuario = self.crear_por_formulario()
        PerfilUsuario.objects.filter(usuario=usuario).update(debe_cambiar_password=False)
        self.client.force_login(self.admin)
        self.client.post(reverse("seguridad:usuario_password", args=[usuario.pk]), {
            "new_password1": "Otra-Temporal-2026",
            "new_password2": "Otra-Temporal-2026",
        })
        usuario.refresh_from_db()
        self.assertTrue(usuario.perfil.debe_cambiar_password)

    def test_CP_PWD_006_puede_cerrar_sesion(self):
        """CP-PWD-006 (borde): con clave temporal igual puede cerrar sesión."""
        usuario = self.crear_por_formulario()
        self.client.login(username=usuario.username, password=CLAVE_TEMPORAL)
        respuesta = self.client.post(reverse("seguridad:logout"))
        self.assertNotEqual(respuesta.get("Location"), reverse("seguridad:cambiar_password"))
        self.assertNotIn("_auth_user_id", self.client.session)
