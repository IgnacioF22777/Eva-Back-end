"""
Evaluación 3 - Mantenedor de tipos y subtipos de atención social (pauta,
Actividad 1: CRUD con validaciones sobre «tipos y subtipos de atención»).

Casos CP-TAT-001 a CP-TAT-012.
"""
from django.core.exceptions import ValidationError
from django.urls import reverse

from .models import AtencionSocial, SubtipoAtencion, TipoAtencion
from .tests import BaseAtencion


class PruebasCatalogoInicial(BaseAtencion):

    def test_cp_tat_001_migracion_carga_los_valores_de_la_matriz(self):
        self.assertEqual(
            set(TipoAtencion.objects.values_list("codigo", flat=True)),
            {"INFORME", "SUBSIDIO", "DERIVACION", "OTRA"},
        )
        self.assertEqual(
            set(SubtipoAtencion.objects.filter(tipo__codigo="SUBSIDIO").values_list("codigo", flat=True)),
            {"IPS", "PGU", "SUF", "SAP"},
        )
        self.assertTrue(TipoAtencion.objects.get(codigo="DERIVACION").exige_destino)

    def test_cp_tat_002_nombres_se_muestran_desde_el_mantenedor(self):
        atencion = self.atencion()
        self.assertEqual(atencion.get_tipo_display(), "Gestión de subsidio")
        self.assertEqual(atencion.get_subtipo_display(), "PGU (Pensión Garantizada Universal)")
        TipoAtencion.objects.filter(codigo="SUBSIDIO").update(nombre="Subsidios del Estado")
        self.assertEqual(atencion.get_tipo_display(), "Subsidios del Estado")


class PruebasMantenedorTipos(BaseAtencion):

    def test_cp_tat_003_administrador_crea_tipo_y_subtipo_nuevos(self):
        self.client.force_login(self.admin)
        self.client.post(reverse("atencion_social:tipo_crear"), {"codigo": "visita dom", "nombre": "Visita domiciliaria"})
        tipo = TipoAtencion.objects.get(codigo="VISITA_DOM")
        self.client.post(reverse("atencion_social:subtipo_crear"), {"tipo": tipo.pk, "codigo": "adulto_mayor", "nombre": "Adulto mayor"})
        self.assertTrue(SubtipoAtencion.objects.filter(codigo="ADULTO_MAYOR", tipo=tipo).exists())

    def test_cp_tat_004_el_tipo_nuevo_se_usa_en_una_atencion(self):
        tipo = TipoAtencion.objects.create(codigo="VISITA", nombre="Visita domiciliaria")
        SubtipoAtencion.objects.create(tipo=tipo, codigo="AM", nombre="Adulto mayor")
        self.client.force_login(self.gestor)
        respuesta = self.client.post(
            reverse("atencion_social:atencion_crear"), self.datos_post(tipo="VISITA", subtipo="AM"),
        )
        self.assertRedirects(respuesta, reverse("atencion_social:atencion_lista"))
        self.assertTrue(AtencionSocial.objects.filter(tipo="VISITA", subtipo="AM").exists())

    def test_cp_tat_005_codigo_duplicado_se_rechaza(self):
        self.client.force_login(self.admin)
        respuesta = self.client.post(reverse("atencion_social:tipo_crear"), {"codigo": "informe", "nombre": "Otro"})
        self.assertContains(respuesta, "Ya existe un tipo con este código.")

    def test_cp_tat_006_codigo_no_se_cambia_al_editar(self):
        tipo = TipoAtencion.objects.get(codigo="OTRA")
        self.client.force_login(self.admin)
        self.client.post(reverse("atencion_social:tipo_editar", args=[tipo.pk]), {"codigo": "CAMBIADO", "nombre": "Otras gestiones"})
        tipo.refresh_from_db()
        self.assertEqual(tipo.codigo, "OTRA")
        self.assertEqual(tipo.nombre, "Otras gestiones")

    def test_cp_tat_007_tipo_con_subtipos_vigentes_no_se_da_de_baja(self):
        tipo = TipoAtencion.objects.get(codigo="SUBSIDIO")
        self.client.force_login(self.admin)
        self.client.post(reverse("atencion_social:tipo_cambiar_estado", args=[tipo.pk]))
        tipo.refresh_from_db()
        self.assertTrue(tipo.activo)

    def test_cp_tat_008_tipo_de_baja_no_se_ofrece_en_registros_nuevos(self):
        TipoAtencion.objects.filter(codigo="OTRA").update(activo=False)
        with self.assertRaises(ValidationError) as error:
            self.atencion(tipo="OTRA", subtipo="").full_clean()
        self.assertIn("tipo", error.exception.message_dict)
        self.client.force_login(self.gestor)
        formulario = self.client.get(reverse("atencion_social:atencion_crear")).context["form"]
        self.assertNotIn("OTRA", dict(formulario.fields["tipo"].choices))

    def test_cp_tat_009_registro_antiguo_con_tipo_de_baja_sigue_editable(self):
        atencion = self.atencion(tipo="OTRA", subtipo="")
        atencion.save()
        TipoAtencion.objects.filter(codigo="OTRA").update(activo=False)
        atencion.detalle = "Se agrega el detalle"
        atencion.full_clean()

    def test_cp_tat_010_subtipo_de_baja_ya_no_es_valido(self):
        SubtipoAtencion.objects.filter(codigo="SAP").update(activo=False)
        with self.assertRaises(ValidationError) as error:
            self.atencion(subtipo="SAP").full_clean()
        self.assertIn("subtipo", error.exception.message_dict)

    def test_cp_tat_011_tipo_nuevo_que_exige_destino(self):
        TipoAtencion.objects.create(codigo="OFICIO", nombre="Oficio a institución", exige_destino=True)
        with self.assertRaises(ValidationError) as error:
            self.atencion(tipo="OFICIO", subtipo="", derivada_a="").full_clean()
        self.assertIn("derivada_a", error.exception.message_dict)

    def test_cp_tat_012_permisos_del_mantenedor(self):
        self.client.force_login(self.supervisor)
        self.assertEqual(self.client.get(reverse("atencion_social:tipo_lista")).status_code, 200)
        self.assertEqual(self.client.get(reverse("atencion_social:tipo_crear")).status_code, 403)
        self.client.force_login(self.gestor)
        self.assertEqual(self.client.get(reverse("atencion_social:tipo_lista")).status_code, 403)
