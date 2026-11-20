"""
Evaluación 3 - Tipos de atención social (RC-05, HU-34, CU-E3-03).

Cada prueba tiene un ID CP-ATS-xxx para la matriz de resultado esperado
vs. obtenido del informe. Se incluyen casos normales y de borde.
"""
from datetime import timedelta

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from delegacionesAPP.models import Delegacion
from seguridadAPP.perfiles import ADMINISTRADOR, ADMINISTRATIVO, SUPERVISOR
from seguridadAPP.roles import sincronizar_roles
from tubo_gestionAPP.tests import crear_usuario

from .models import DERIVACION, INFORME, OTRA, SUBSIDIO, SUBTIPOS_POR_TIPO, AtencionSocial


class BaseAtencion(TestCase):

    @classmethod
    def setUpTestData(cls):
        sincronizar_roles()
        cls.centro = Delegacion.objects.create(
            nombre="Delegación Centro", direccion="Dir", encargado="Enc",
            email="c@laserena.cl", telefono="1", celular="1",
        )
        cls.pampa = Delegacion.objects.create(
            nombre="Delegación La Pampa", direccion="Dir", encargado="Enc",
            email="p@laserena.cl", telefono="1", celular="1",
        )
        cls.admin = crear_usuario("11.111.111-1", "admin@laserena.cl", ADMINISTRADOR)
        cls.supervisor = crear_usuario("12.345.678-5", "sup@laserena.cl", SUPERVISOR, delegacion=cls.centro)
        cls.gestor = crear_usuario("22.222.222-2", "gestor@laserena.cl", ADMINISTRATIVO, delegacion=cls.centro)

    def atencion(self, **cambios):
        datos = {
            "delegacion": self.centro, "fecha": timezone.localdate(), "tipo": SUBSIDIO,
            "subtipo": "PGU", "nombre_vecino": "María Pérez", "telefono_vecino": "+56 9 1234 5678",
        }
        datos.update(cambios)
        return AtencionSocial(**datos)

    def datos_post(self, **cambios):
        datos = {
            "delegacion": self.centro.pk, "fecha": timezone.localdate().isoformat(), "tipo": INFORME,
            "subtipo": "APORTE_ECONOMICO", "nombre_vecino": "Juan Soto", "telefono_vecino": "912345678",
            "derivada_a": "", "detalle": "",
        }
        datos.update(cambios)
        return datos


class PruebasReglas(BaseAtencion):

    def test_CP_ATS_001_combinaciones_validas(self):
        """CP-ATS-001: cada subtipo de informes y subsidios se acepta con su tipo."""
        for tipo, subtipos in SUBTIPOS_POR_TIPO.items():
            for subtipo in subtipos:
                self.atencion(tipo=tipo, subtipo=subtipo).full_clean()
        self.atencion(tipo=OTRA, subtipo="").full_clean()

    def test_CP_ATS_002_subtipo_incoherente(self):
        """CP-ATS-002 (borde): un subtipo de otro tipo se rechaza (informe con PGU, subsidio con aporte material)."""
        for tipo, subtipo in ((INFORME, "PGU"), (SUBSIDIO, "APORTE_MATERIAL"), (OTRA, "SAP")):
            with self.assertRaises(ValidationError) as error:
                self.atencion(tipo=tipo, subtipo=subtipo).full_clean()
            self.assertIn("subtipo", error.exception.message_dict)

    def test_CP_ATS_003_subtipo_obligatorio(self):
        """CP-ATS-003 (borde): informes y subsidios sin subtipo se rechazan."""
        for tipo in (INFORME, SUBSIDIO):
            with self.assertRaises(ValidationError) as error:
                self.atencion(tipo=tipo, subtipo="").full_clean()
            self.assertIn("subtipo", error.exception.message_dict)

    def test_CP_ATS_004_derivacion_requiere_destino(self):
        """CP-ATS-004 (borde): una derivación sin destino (o solo con espacios) se rechaza; con destino se acepta."""
        for destino in ("", "   "):
            with self.assertRaises(ValidationError) as error:
                self.atencion(tipo=DERIVACION, subtipo="", derivada_a=destino).full_clean()
            self.assertIn("derivada_a", error.exception.message_dict)
        self.atencion(tipo=DERIVACION, subtipo="", derivada_a="CESFAM Cardenal Caro").full_clean()

    def test_CP_ATS_005_fecha_futura(self):
        """CP-ATS-005 (borde): la fecha de hoy se acepta; la de mañana se rechaza."""
        self.atencion(fecha=timezone.localdate()).full_clean()
        with self.assertRaises(ValidationError) as error:
            self.atencion(fecha=timezone.localdate() + timedelta(days=1)).full_clean()
        self.assertIn("fecha", error.exception.message_dict)

    def test_CP_ATS_006_telefono_y_tipo_invalidos(self):
        """CP-ATS-006 (borde): teléfono con letras y tipo desconocido se rechazan; el teléfono es opcional."""
        with self.assertRaises(ValidationError) as error:
            self.atencion(telefono_vecino="abc123").full_clean()
        self.assertIn("telefono_vecino", error.exception.message_dict)
        with self.assertRaises(ValidationError) as error:
            self.atencion(tipo="BECA", subtipo="").full_clean()
        self.assertIn("tipo", error.exception.message_dict)
        self.atencion(telefono_vecino="").full_clean()


class PruebasVistas(BaseAtencion):

    def test_CP_ATS_007_gestor_registra_en_su_delegacion(self):
        """CP-ATS-007: el Administrativo (Gestor Social) registra una atención en su delegación."""
        self.client.force_login(self.gestor)
        respuesta = self.client.post(reverse("atencion_social:atencion_crear"), self.datos_post())
        self.assertRedirects(respuesta, reverse("atencion_social:atencion_lista"))
        atencion = AtencionSocial.objects.get()
        self.assertEqual(atencion.delegacion, self.centro)
        self.assertEqual(atencion.registrada_por, self.gestor)

    def test_CP_ATS_008_rechazos_en_el_formulario(self):
        """CP-ATS-008 (borde): delegación ajena y subtipo incoherente enviados a mano se rechazan sin guardar."""
        self.client.force_login(self.gestor)
        url = reverse("atencion_social:atencion_crear")
        respuesta = self.client.post(url, self.datos_post(delegacion=self.pampa.pk))
        self.assertIn("delegacion", respuesta.context["form"].errors)
        respuesta = self.client.post(url, self.datos_post(subtipo="SUF"))
        self.assertIn("subtipo", respuesta.context["form"].errors)
        self.assertFalse(AtencionSocial.objects.exists())

    def test_CP_ATS_009_listado_por_delegacion(self):
        """CP-ATS-009: el listado y el resumen muestran solo la delegación propia; el Administrador ve todas."""
        self.atencion(nombre_vecino="VECINA CENTRO").save()
        self.atencion(delegacion=self.pampa, nombre_vecino="VECINO PAMPA").save()
        url = reverse("atencion_social:atencion_lista")

        self.client.force_login(self.gestor)
        respuesta = self.client.get(url, {"delegacion": self.pampa.pk})
        self.assertContains(respuesta, "VECINA CENTRO")
        self.assertNotContains(respuesta, "VECINO PAMPA")
        self.assertEqual(dict((v, n) for v, _, n in respuesta.context["resumen"])[SUBSIDIO], 1)

        self.client.force_login(self.admin)
        respuesta = self.client.get(url)
        self.assertContains(respuesta, "VECINO PAMPA")
        self.assertEqual(respuesta.context["total_filtradas"], 2)

    def test_CP_ATS_010_otra_delegacion_es_403(self):
        """CP-ATS-010 (borde): editar o dar de baja una atención de otra delegación es 403."""
        ajena = self.atencion(delegacion=self.pampa)
        ajena.save()
        self.client.force_login(self.supervisor)
        self.assertEqual(self.client.get(reverse("atencion_social:atencion_editar", args=[ajena.pk])).status_code, 403)
        self.assertEqual(
            self.client.post(reverse("atencion_social:atencion_cambiar_estado", args=[ajena.pk])).status_code, 403
        )
        ajena.refresh_from_db()
        self.assertTrue(ajena.activo)

    def test_CP_ATS_011_baja_logica_solo_supervisor(self):
        """CP-ATS-011: el Supervisor da de baja y reactiva (el registro se conserva); el Administrativo no puede."""
        propia = self.atencion()
        propia.save()
        url = reverse("atencion_social:atencion_cambiar_estado", args=[propia.pk])

        self.client.force_login(self.gestor)
        self.assertEqual(self.client.post(url).status_code, 403)

        self.client.force_login(self.supervisor)
        self.client.post(url)
        propia.refresh_from_db()
        self.assertFalse(propia.activo)
        self.client.post(url)
        propia.refresh_from_db()
        self.assertTrue(propia.activo)

    def test_CP_ATS_012_filtros_por_tipo_y_busqueda(self):
        """CP-ATS-012: filtra por tipo y busca por vecino o destino; un tipo inválido muestra todo."""
        self.atencion(nombre_vecino="ANA ROJAS").save()
        self.atencion(tipo=DERIVACION, subtipo="", derivada_a="OPD La Serena", nombre_vecino="LUIS DIAZ").save()
        self.client.force_login(self.gestor)
        url = reverse("atencion_social:atencion_lista")

        respuesta = self.client.get(url, {"tipo": DERIVACION})
        self.assertContains(respuesta, "LUIS DIAZ")
        self.assertNotContains(respuesta, "ANA ROJAS")
        respuesta = self.client.get(url, {"q": "opd"})
        self.assertEqual(respuesta.context["total_filtradas"], 1)
        respuesta = self.client.get(url, {"tipo": "XYZ"})
        self.assertEqual(respuesta.context["total_filtradas"], 2)

    def test_CP_ATS_013_sin_sesion_y_sin_delegacion(self):
        """CP-ATS-013 (borde): sin sesión redirige al login; sin delegación no ve ni registra atenciones."""
        url = reverse("atencion_social:atencion_lista")
        self.assertEqual(self.client.get(url).status_code, 302)

        self.atencion().save()
        sin_delegacion = crear_usuario("13.131.313-6", "sindel@laserena.cl", ADMINISTRATIVO)
        self.client.force_login(sin_delegacion)
        self.assertEqual(self.client.get(url).context["total_filtradas"], 0)
        self.assertEqual(self.client.get(reverse("atencion_social:atencion_crear")).status_code, 403)
