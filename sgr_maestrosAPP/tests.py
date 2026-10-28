from datetime import date

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse

from seguridadAPP.models import PerfilUsuario, normalizar_rut
from seguridadAPP.perfiles import (
    ADMINISTRADOR,
    ADMINISTRATIVO,
    SUPERVISOR,
)
from seguridadAPP.roles import sincronizar_roles

from .models import (
    CatalogoActividad,
    DetallePeriodo,
    Meta,
    Periodo,
)


User = get_user_model()

CLAVE = "ClaveSegura#2026"


def crear_usuario(rut, email, rol):
    usuario = User.objects.create_user(
        username=normalizar_rut(rut),
        email=email,
        password=CLAVE,
    )
    PerfilUsuario.objects.create(usuario=usuario, rut=normalizar_rut(rut))
    usuario.groups.add(Group.objects.get(name=rol))

    return usuario


class PruebasMaestros(TestCase):
    """Búsqueda y baja lógica en las tablas maestras del SGR."""

    @classmethod
    def setUpTestData(cls):
        sincronizar_roles()

        cls.admin = crear_usuario(
            "11.111.111-1", "admin@laserena.cl", ADMINISTRADOR
        )
        cls.supervisor = crear_usuario(
            "12.345.678-5", "supervisor@laserena.cl", SUPERVISOR
        )
        cls.administrativo = crear_usuario(
            "22.222.222-2", "administrativo@laserena.cl", ADMINISTRATIVO
        )

        cls.periodo = Periodo.objects.create(
            codigo="2026",
            nombre="Período 2026",
            fecha_inicio=date(2026, 1, 1),
            fecha_fin=date(2026, 12, 31),
        )
        cls.actividad = CatalogoActividad.objects.create(
            codigo="ACT-001",
            nombre="Aseo y ornato",
            area="Operaciones",
        )
        cls.actividad_inactiva = CatalogoActividad.objects.create(
            codigo="ACT-002",
            nombre="Iluminación histórica",
            area="Operaciones",
            activo=False,
        )

    # --- CATÁLOGO DE ACTIVIDADES ---
    def test_catalogo_requiere_sesion(self):
        respuesta = self.client.get(reverse("sgr_maestros:catalogo_lista"))
        self.assertEqual(respuesta.status_code, 302)

    def test_catalogo_busca_por_codigo_nombre_y_area(self):
        self.client.force_login(self.supervisor)

        respuesta = self.client.get(
            reverse("sgr_maestros:catalogo_lista"), {"q": "ACT-001"}
        )
        self.assertContains(respuesta, "Aseo y ornato")
        self.assertNotContains(respuesta, "Iluminación histórica")

        respuesta = self.client.get(
            reverse("sgr_maestros:catalogo_lista"), {"q": "Operaciones"}
        )
        self.assertContains(respuesta, "Aseo y ornato")

    def test_catalogo_filtra_por_estado(self):
        self.client.force_login(self.supervisor)

        respuesta = self.client.get(
            reverse("sgr_maestros:catalogo_lista"),
            {"estado": "inactivos"},
        )
        self.assertContains(respuesta, "Iluminación histórica")
        self.assertNotContains(respuesta, "Aseo y ornato")

    def test_catalogo_se_consulta_pero_no_se_edita_como_administrativo(self):
        self.client.force_login(self.administrativo)

        respuesta = self.client.get(reverse("sgr_maestros:catalogo_lista"))
        self.assertEqual(respuesta.status_code, 200)

        respuesta = self.client.get(reverse("sgr_maestros:catalogo_crear"))
        self.assertEqual(respuesta.status_code, 403)

    # --- METAS ---
    def test_meta_busca_por_nombre_codigo_y_actividad(self):
        Meta.objects.create(
            codigo="META-001",
            nombre="Reducir reclamos por luminarias",
            periodo=self.periodo,
            actividad=self.actividad,
            valor_objetivo=10,
            ponderacion=50,
        )
        Meta.objects.create(
            codigo="META-002",
            nombre="Aumentar cobertura de aseo",
            periodo=self.periodo,
            actividad=self.actividad_inactiva,
            valor_objetivo=20,
            ponderacion=50,
        )
        self.client.force_login(self.supervisor)

        respuesta = self.client.get(
            reverse("sgr_maestros:meta_lista"), {"q": "luminarias"}
        )
        self.assertContains(respuesta, "Reducir reclamos por luminarias")
        self.assertNotContains(respuesta, "Aumentar cobertura de aseo")

        respuesta = self.client.get(
            reverse("sgr_maestros:meta_lista"), {"q": "META-002"}
        )
        self.assertContains(respuesta, "Aumentar cobertura de aseo")
        self.assertNotContains(respuesta, "Reducir reclamos por luminarias")

    def test_meta_filtra_por_estado(self):
        Meta.objects.create(
            codigo="META-001",
            nombre="Meta activa",
            periodo=self.periodo,
            actividad=self.actividad,
            valor_objetivo=10,
            ponderacion=50,
        )
        Meta.objects.create(
            codigo="META-002",
            nombre="Meta histórica",
            periodo=self.periodo,
            actividad=self.actividad,
            valor_objetivo=20,
            ponderacion=50,
            activo=False,
        )
        self.client.force_login(self.supervisor)

        respuesta = self.client.get(
            reverse("sgr_maestros:meta_lista"), {"estado": "inactivos"}
        )
        self.assertContains(respuesta, "Meta histórica")
        self.assertNotContains(respuesta, "Meta activa")

    # --- DETALLES DE PERÍODO ---
    def crear_detalle(self, **cambios):
        datos = {
            "periodo": self.periodo,
            "nombre": "Primer semestre",
            "fecha_inicio": date(2026, 1, 1),
            "fecha_fin": date(2026, 6, 30),
        }
        datos.update(cambios)

        return DetallePeriodo.objects.create(**datos)

    def test_detalle_busca_por_nombre_y_periodo(self):
        detalle = self.crear_detalle()
        self.client.force_login(self.supervisor)

        respuesta = self.client.get(
            reverse("sgr_maestros:detalle_periodo_lista"),
            {"q": "primer semestre"},
        )
        self.assertContains(respuesta, "Primer semestre")

        respuesta = self.client.get(
            reverse("sgr_maestros:detalle_periodo_lista"), {"q": "2026"}
        )
        self.assertContains(respuesta, detalle.nombre)

    def test_detalle_baja_logica_conserva_el_registro(self):
        detalle = self.crear_detalle()
        self.client.force_login(self.supervisor)

        respuesta = self.client.post(
            reverse(
                "sgr_maestros:detalle_periodo_eliminar", args=[detalle.pk]
            )
        )

        self.assertRedirects(
            respuesta, reverse("sgr_maestros:detalle_periodo_lista")
        )

        detalle.refresh_from_db()
        self.assertFalse(detalle.activo)
        self.assertTrue(
            DetallePeriodo.objects.filter(pk=detalle.pk).exists()
        )

    def test_detalle_reactivacion(self):
        detalle = self.crear_detalle(activo=False)
        self.client.force_login(self.supervisor)

        self.client.post(
            reverse(
                "sgr_maestros:detalle_periodo_eliminar", args=[detalle.pk]
            )
        )

        detalle.refresh_from_db()
        self.assertTrue(detalle.activo)

    def test_detalle_de_periodo_cerrado_no_se_modifica(self):
        periodo_cerrado = Periodo.objects.create(
            codigo="2025",
            nombre="Período 2025",
            fecha_inicio=date(2025, 1, 1),
            fecha_fin=date(2025, 12, 31),
            cerrado=True,
        )
        detalle = DetallePeriodo.objects.create(
            periodo=periodo_cerrado,
            nombre="Detalle 2025",
            fecha_inicio=date(2025, 1, 1),
            fecha_fin=date(2025, 6, 30),
        )
        self.client.force_login(self.supervisor)

        respuesta = self.client.post(
            reverse(
                "sgr_maestros:detalle_periodo_eliminar", args=[detalle.pk]
            ),
            follow=True,
        )

        self.assertContains(respuesta, "períodos cerrados")

        detalle.refresh_from_db()
        self.assertTrue(detalle.activo)

    def test_no_duplica_detalle_activo(self):
        self.crear_detalle()
        self.client.force_login(self.supervisor)

        respuesta = self.client.post(
            reverse("sgr_maestros:detalle_periodo_crear"),
            {
                "periodo": self.periodo.pk,
                "nombre": "Primer semestre",
                "fecha_inicio": "2026-01-01",
                "fecha_fin": "2026-06-30",
                "dias_computables": 120,
                "observaciones": "",
            },
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(
            respuesta,
            "Ya existe un detalle activo con este nombre",
        )
        self.assertEqual(
            DetallePeriodo.objects.filter(
                periodo=self.periodo, nombre="Primer semestre"
            ).count(),
            1,
        )

    def test_crear_reactiva_detalle_inactivo(self):
        inactivo = self.crear_detalle(activo=False)
        self.client.force_login(self.supervisor)

        respuesta = self.client.post(
            reverse("sgr_maestros:detalle_periodo_crear"),
            {
                "periodo": self.periodo.pk,
                "nombre": "Primer semestre",
                "fecha_inicio": "2026-01-01",
                "fecha_fin": "2026-06-30",
                "dias_computables": 120,
                "observaciones": "Reactivado",
            },
        )

        self.assertRedirects(
            respuesta, reverse("sgr_maestros:detalle_periodo_lista")
        )

        inactivo.refresh_from_db()
        self.assertTrue(inactivo.activo)
        self.assertEqual(inactivo.observaciones, "Reactivado")
        self.assertEqual(
            DetallePeriodo.objects.filter(
                periodo=self.periodo, nombre="Primer semestre"
            ).count(),
            1,
        )

    def test_administrativo_no_gestiona_detalles(self):
        detalle = self.crear_detalle()
        self.client.force_login(self.administrativo)

        respuesta = self.client.get(
            reverse("sgr_maestros:detalle_periodo_lista")
        )
        self.assertEqual(respuesta.status_code, 200)

        respuesta = self.client.get(
            reverse("sgr_maestros:detalle_periodo_crear")
        )
        self.assertEqual(respuesta.status_code, 403)

        respuesta = self.client.post(
            reverse(
                "sgr_maestros:detalle_periodo_eliminar", args=[detalle.pk]
            )
        )
        self.assertEqual(respuesta.status_code, 403)

        detalle.refresh_from_db()
        self.assertTrue(detalle.activo)
