"""
Evaluación 3 - Configuración de felicitaciones y reclamos (R8).
Responsable: Camilo Villalobos.

Respuesta del profesor: el descuento por reclamo va "entre 20 y 30%" y
debe ser configurable, con una opción para limitar o no las
felicitaciones al tope de 120%.
"""

from decimal import Decimal as D

from django.contrib.auth.models import Group, User
from django.core.exceptions import ValidationError
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from delegacionesAPP.models import Delegacion
from seguridadAPP.models import PerfilUsuario, normalizar_rut
from seguridadAPP.perfiles import ADMINISTRADOR, SUPERVISOR
from seguridadAPP.roles import sincronizar_roles

from .models import AjusteDesempeno, ConfiguracionMatriz
from .reglas import aplicar_ajustes
from .servicios import cumplimiento_final


def crear_funcionario(rut, perfil, delegacion=None):
    usuario = User.objects.create_user(username=normalizar_rut(rut), password="Clave-Segura-2026")
    PerfilUsuario.objects.create(usuario=usuario, rut=normalizar_rut(rut), delegacion=delegacion)
    usuario.groups.add(Group.objects.get(name=perfil))
    return usuario


class PruebasReglaLimitarFelicitaciones(SimpleTestCase):

    def test_CP_CFG_003_sin_limite_las_felicitaciones_superan_el_tope(self):
        """CP-CFG-003 (borde): 120% + 1 felicitación = 130% si no se limita."""
        self.assertEqual(aplicar_ajustes(D("1.20"), 1, 0, limitar_felicitaciones=False), D("1.30"))
        self.assertEqual(aplicar_ajustes(D("1.20"), 1, 0, limitar_felicitaciones=True), D("1.20"))

    def test_CP_CFG_004_sin_limite_el_tope_igual_aplica_al_puntaje_base(self):
        """CP-CFG-004: sin límite, el puntaje base sigue topado en 120% antes de sumar."""
        self.assertEqual(aplicar_ajustes(D("1.50"), 1, 0, limitar_felicitaciones=False), D("1.30"))

    def test_CP_CFG_005_sin_limite_los_reclamos_se_descuentan_primero(self):
        """CP-CFG-005: 100% − 1 reclamo (25%) + 1 felicitación = 85%."""
        self.assertEqual(
            aplicar_ajustes(D("1.00"), 1, 1, descuento=D("0.25"), limitar_felicitaciones=False),
            D("0.85"),
        )


class PruebasConfiguracion(TestCase):

    @classmethod
    def setUpTestData(cls):
        sincronizar_roles()
        cls.centro = Delegacion.objects.create(
            nombre="Centro", direccion="Dirección", encargado="Encargado",
            email="centro@laserena.cl", telefono="512000000", celular="912345678",
        )
        cls.admin = crear_funcionario("11.111.111-1", ADMINISTRADOR)
        cls.delegado = crear_funcionario("12.345.678-5", SUPERVISOR, cls.centro)

    def test_CP_CFG_001_valores_por_defecto(self):
        """CP-CFG-001: sin configurar, reclamo 20%, felicitación 10% y con límite."""
        config = ConfiguracionMatriz.obtener()
        self.assertEqual(config.descuento_reclamo_pct, 20)
        self.assertEqual(config.bono_felicitacion_pct, 10)
        self.assertTrue(config.limitar_felicitaciones_al_tope)

    def test_CP_CFG_002_descuento_fuera_de_rango(self):
        """CP-CFG-002 (borde): 19% y 31% se rechazan; 20% y 30% se aceptan."""
        config = ConfiguracionMatriz.obtener()
        for valor in (19, 31):
            config.descuento_reclamo_pct = valor
            with self.assertRaises(ValidationError):
                config.full_clean()
        for valor in (20, 30):
            config.descuento_reclamo_pct = valor
            config.full_clean()

    def test_CP_CFG_006_siempre_una_sola_configuracion(self):
        """CP-CFG-006: guardar otra configuración reemplaza la única fila."""
        ConfiguracionMatriz(descuento_reclamo_pct=25).save()
        ConfiguracionMatriz(descuento_reclamo_pct=30).save()
        self.assertEqual(ConfiguracionMatriz.objects.count(), 1)
        self.assertEqual(ConfiguracionMatriz.obtener().descuento_reclamo_pct, 30)

    def test_CP_CFG_007_el_puntaje_final_usa_la_configuracion(self):
        """CP-CFG-007: con reclamo al 30%, 100% con un reclamo queda en 70%."""
        from datetime import date
        from django.core.files.uploadedfile import SimpleUploadedFile

        maria = crear_funcionario("22.222.222-2", "Administrativo", self.centro)
        with self.settings(MEDIA_ROOT=__import__("tempfile").mkdtemp()):
            AjusteDesempeno.objects.create(
                tipo=AjusteDesempeno.RECLAMO, funcionario=maria, fecha=date(2026, 8, 10),
                medio="CORREO_DELEGADO", remitente_nombre="Vecino", remitente_contacto="912345678",
                descripcion="Detalle", registrado_por=self.delegado,
                respaldo=SimpleUploadedFile("r.png", b"x", content_type="image/png"),
            )
        desde, hasta = date(2026, 7, 1), date(2026, 9, 30)

        self.assertEqual(cumplimiento_final(maria, D("1.00"), desde, hasta), D("0.80"))

        config = ConfiguracionMatriz.obtener()
        config.descuento_reclamo_pct = 30
        config.save()
        self.assertEqual(cumplimiento_final(maria, D("1.00"), desde, hasta), D("0.70"))

    def test_CP_CFG_008_admin_guarda_la_configuracion(self):
        """CP-CFG-008: el Administrador cambia el descuento y desactiva el límite."""
        self.client.force_login(self.admin)
        pantalla = self.client.get(reverse("matriz:configuracion"))
        self.assertContains(pantalla, "Descuento por reclamo")

        respuesta = self.client.post(reverse("matriz:configuracion"), {
            "descuento_reclamo_pct": 25, "bono_felicitacion_pct": 10,
        })
        self.assertRedirects(respuesta, reverse("matriz:configuracion"))

        config = ConfiguracionMatriz.obtener()
        self.assertEqual(config.descuento_reclamo_pct, 25)
        self.assertFalse(config.limitar_felicitaciones_al_tope)
        self.assertEqual(config.actualizado_por, self.admin)

        # Los listados muestran el porcentaje nuevo.
        listado = self.client.get(reverse("matriz:ajuste_lista"))
        self.assertContains(listado, "reclamo −25%")

    def test_CP_CFG_009_formulario_rechaza_35_por_ciento(self):
        """CP-CFG-009 (borde): por pantalla tampoco se acepta un 35%."""
        self.client.force_login(self.admin)
        respuesta = self.client.post(reverse("matriz:configuracion"), {
            "descuento_reclamo_pct": 35, "bono_felicitacion_pct": 10,
            "limitar_felicitaciones_al_tope": "on",
        })
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(ConfiguracionMatriz.obtener().descuento_reclamo_pct, 20)

    def test_CP_CFG_010_supervisor_no_puede_configurar(self):
        """CP-CFG-010 (seguridad): el delegado recibe 403 y no cambia nada."""
        self.client.force_login(self.delegado)
        self.assertEqual(self.client.get(reverse("matriz:configuracion")).status_code, 403)
        respuesta = self.client.post(reverse("matriz:configuracion"), {
            "descuento_reclamo_pct": 30, "bono_felicitacion_pct": 50,
        })
        self.assertEqual(respuesta.status_code, 403)
        self.assertEqual(ConfiguracionMatriz.obtener().descuento_reclamo_pct, 20)
