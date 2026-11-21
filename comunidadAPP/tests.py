"""
Evaluación 3 - Territorios, vecinos, membresía y dirigencia en juntas de
vecinos, e hitos con responsable (pauta, Actividades 1 y 2).

Cada prueba tiene un ID para la matriz de resultado esperado vs. obtenido:
CP-TER (territorios), CP-VEC (vecinos y autocompletado), CP-MEM
(membresías) y CP-HIT (hitos). Incluye casos positivos, negativos,
límites, permisos y ámbito por delegación.
"""
from datetime import date, timedelta

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from delegacionesAPP.models import Delegacion
from organizacionesAPP.models import OrganizacionComunitaria
from seguridadAPP.perfiles import ADMINISTRADOR, ADMINISTRATIVO, SUPERVISOR
from seguridadAPP.roles import sincronizar_roles
from tubo_gestionAPP.tests import CLAVE, crear_usuario

from .models import Hito, MembresiaJunta, Territorio, Vecino


RUT_VECINO = "12.345.678-5"
RUT_VECINO_2 = "11.111.111-1"


class BaseComunidad(TestCase):

    @classmethod
    def setUpTestData(cls):
        sincronizar_roles()
        cls.centro = Delegacion.objects.create(
            nombre="Delegación Centro", direccion="Dir", encargado="Enc",
            email="centro@laserena.cl", telefono="512000001", celular="912000001",
        )
        cls.pampa = Delegacion.objects.create(
            nombre="Delegación La Pampa", direccion="Dir", encargado="Enc",
            email="pampa@laserena.cl", telefono="512000002", celular="912000002",
        )

        cls.admin = crear_usuario("21.988.036-7", "admin@laserena.cl", ADMINISTRADOR)
        cls.supervisor = crear_usuario("21.345.678-4", "sup@laserena.cl", SUPERVISOR, cls.centro)
        cls.administrativo = crear_usuario("22.456.789-8", "adm@laserena.cl", ADMINISTRATIVO, cls.centro)
        cls.supervisor_pampa = crear_usuario("19.876.543-0", "sup2@laserena.cl", SUPERVISOR, cls.pampa)

        cls.territorio = Territorio.objects.create(nombre="Unidad Vecinal 14", delegacion=cls.centro)
        cls.territorio_pampa = Territorio.objects.create(nombre="Villa Pampa", delegacion=cls.pampa)

        cls.vecino = Vecino.objects.create(
            rut="12345678-5", nombre="María Pérez", telefono="912345678",
            delegacion=cls.centro, territorio=cls.territorio,
        )
        cls.junta = OrganizacionComunitaria.objects.create(
            nombre="Junta de Vecinos El Indio", tipo=OrganizacionComunitaria.JUNTA_VECINOS,
            numero_registro="4006", delegacion=cls.centro,
        )

    def entrar(self, usuario):
        self.client.force_login(usuario)


# ============================================================
# TERRITORIOS
# ============================================================

class PruebasTerritorios(BaseComunidad):

    def test_cp_ter_001_supervisor_crea_territorio_en_su_delegacion(self):
        self.entrar(self.supervisor)
        respuesta = self.client.post(reverse("comunidad:territorio_crear"), {
            "nombre": "Sector Las Rojas", "delegacion": self.centro.pk, "descripcion": "",
        })
        self.assertRedirects(respuesta, reverse("comunidad:territorio_lista"))
        self.assertTrue(Territorio.objects.filter(nombre="Sector Las Rojas", delegacion=self.centro).exists())

    def test_cp_ter_002_no_duplica_nombre_vigente_en_la_delegacion(self):
        territorio = Territorio(nombre="  unidad   vecinal 14 ", delegacion=self.centro)
        with self.assertRaises(ValidationError):
            territorio.full_clean()

    def test_cp_ter_003_mismo_nombre_en_otra_delegacion_es_valido(self):
        Territorio(nombre="Unidad Vecinal 14", delegacion=self.pampa).full_clean()

    def test_cp_ter_004_supervisor_no_crea_en_otra_delegacion(self):
        self.entrar(self.supervisor)
        self.client.post(reverse("comunidad:territorio_crear"), {
            "nombre": "Intruso", "delegacion": self.pampa.pk,
        })
        self.assertFalse(Territorio.objects.filter(nombre="Intruso").exists())

    def test_cp_ter_005_listado_respeta_ambito(self):
        self.entrar(self.supervisor)
        respuesta = self.client.get(reverse("comunidad:territorio_lista"))
        self.assertContains(respuesta, "Unidad Vecinal 14")
        self.assertNotContains(respuesta, "Villa Pampa")

    def test_cp_ter_006_editar_territorio_ajeno_responde_403(self):
        self.entrar(self.supervisor)
        respuesta = self.client.get(reverse("comunidad:territorio_editar", args=[self.territorio_pampa.pk]))
        self.assertEqual(respuesta.status_code, 403)

    def test_cp_ter_007_no_se_da_de_baja_con_vecinos_vigentes(self):
        self.entrar(self.supervisor)
        self.client.post(reverse("comunidad:territorio_cambiar_estado", args=[self.territorio.pk]))
        self.territorio.refresh_from_db()
        self.assertTrue(self.territorio.activo)

    def test_cp_ter_008_baja_logica_y_reactivacion(self):
        vacio = Territorio.objects.create(nombre="Sin uso", delegacion=self.centro)
        self.entrar(self.supervisor)
        url = reverse("comunidad:territorio_cambiar_estado", args=[vacio.pk])
        self.client.post(url)
        vacio.refresh_from_db()
        self.assertFalse(vacio.activo)
        self.client.post(url)
        vacio.refresh_from_db()
        self.assertTrue(vacio.activo)

    def test_cp_ter_009_administrativo_consulta_pero_no_crea(self):
        self.entrar(self.administrativo)
        self.assertEqual(self.client.get(reverse("comunidad:territorio_lista")).status_code, 200)
        self.assertEqual(self.client.get(reverse("comunidad:territorio_crear")).status_code, 403)

    def test_cp_ter_010_busqueda_por_nombre(self):
        Territorio.objects.create(nombre="Población Juan XXIII", delegacion=self.centro)
        self.entrar(self.admin)
        respuesta = self.client.get(reverse("comunidad:territorio_lista"), {"q": "juan"})
        self.assertContains(respuesta, "Población Juan XXIII")
        self.assertNotContains(respuesta, "Unidad Vecinal 14")


# ============================================================
# VECINOS
# ============================================================

class PruebasVecinos(BaseComunidad):

    def datos(self, **cambios):
        datos = {
            "rut": RUT_VECINO_2, "nombre": "Juan Soto", "telefono": "+56 9 8765 4321",
            "correo": "", "direccion": "Calle 1", "delegacion": self.centro.pk,
            "territorio": self.territorio.pk,
        }
        datos.update(cambios)
        return datos

    def test_cp_vec_001_administrativo_registra_vecino_con_rut_normalizado(self):
        self.entrar(self.administrativo)
        respuesta = self.client.post(reverse("comunidad:vecino_crear"), self.datos())
        self.assertRedirects(respuesta, reverse("comunidad:vecino_lista"))
        self.assertTrue(Vecino.objects.filter(rut="11111111-1").exists())

    def test_cp_vec_002_rut_invalido_se_rechaza(self):
        self.entrar(self.administrativo)
        self.client.post(reverse("comunidad:vecino_crear"), self.datos(rut="11.111.111-2"))
        self.assertFalse(Vecino.objects.filter(nombre="Juan Soto").exists())

    def test_cp_vec_003_rut_duplicado_se_rechaza(self):
        self.entrar(self.administrativo)
        respuesta = self.client.post(reverse("comunidad:vecino_crear"), self.datos(rut=RUT_VECINO))
        self.assertContains(respuesta, "Ya existe un vecino registrado con este RUT.")

    def test_cp_vec_004_telefono_debe_tener_nueve_digitos(self):
        vecino = Vecino(rut="11111111-1", nombre="Juan", telefono="1234", delegacion=self.centro)
        with self.assertRaises(ValidationError) as error:
            vecino.full_clean()
        self.assertIn("telefono", error.exception.message_dict)

    def test_cp_vec_005_territorio_debe_ser_de_la_delegacion(self):
        vecino = Vecino(
            rut="11111111-1", nombre="Juan", telefono="912345678",
            delegacion=self.centro, territorio=self.territorio_pampa,
        )
        with self.assertRaises(ValidationError) as error:
            vecino.full_clean()
        self.assertIn("territorio", error.exception.message_dict)

    def test_cp_vec_006_busqueda_por_rut_con_puntos(self):
        self.entrar(self.supervisor)
        respuesta = self.client.get(reverse("comunidad:vecino_lista"), {"q": RUT_VECINO})
        self.assertContains(respuesta, "María Pérez")

    def test_cp_vec_007_administrativo_no_da_de_baja(self):
        self.entrar(self.administrativo)
        respuesta = self.client.post(reverse("comunidad:vecino_cambiar_estado", args=[self.vecino.pk]))
        self.assertEqual(respuesta.status_code, 403)

    def test_cp_vec_008_no_se_da_de_baja_con_membresia_vigente(self):
        MembresiaJunta.objects.create(vecino=self.vecino, organizacion=self.junta)
        self.entrar(self.supervisor)
        self.client.post(reverse("comunidad:vecino_cambiar_estado", args=[self.vecino.pk]))
        self.vecino.refresh_from_db()
        self.assertTrue(self.vecino.activo)

    def test_cp_vec_009_autocompletado_devuelve_datos_por_rut(self):
        self.entrar(self.administrativo)
        respuesta = self.client.get(reverse("comunidad:vecino_buscar"), {"rut": "12.345.678-5"})
        datos = respuesta.json()
        self.assertTrue(datos["encontrado"])
        self.assertEqual(datos["nombre"], "María Pérez")
        self.assertEqual(datos["telefono"], "912345678")

    def test_cp_vec_010_autocompletado_respeta_ambito(self):
        self.entrar(self.supervisor_pampa)
        respuesta = self.client.get(reverse("comunidad:vecino_buscar"), {"rut": RUT_VECINO})
        self.assertFalse(respuesta.json()["encontrado"])

    def test_cp_vec_011_autocompletado_exige_sesion(self):
        respuesta = self.client.get(reverse("comunidad:vecino_buscar"), {"rut": RUT_VECINO})
        self.assertEqual(respuesta.status_code, 302)

    def test_cp_vec_012_autocompletado_no_devuelve_vecinos_de_baja(self):
        self.vecino.activo = False
        self.vecino.save()
        self.entrar(self.admin)
        respuesta = self.client.get(reverse("comunidad:vecino_buscar"), {"rut": RUT_VECINO})
        self.assertFalse(respuesta.json()["encontrado"])

    def test_cp_vec_013_formularios_incluyen_autocompletado(self):
        self.entrar(self.administrativo)
        actividad = self.client.get(reverse("actividades:crear"))
        self.assertContains(actividad, reverse("comunidad:vecino_buscar"))
        atencion = self.client.get(reverse("atencion_social:atencion_crear"))
        self.assertContains(atencion, "rut_autocompletar")

    def test_cp_vec_014_editar_vecino_ajeno_responde_403(self):
        self.entrar(self.supervisor_pampa)
        respuesta = self.client.get(reverse("comunidad:vecino_editar", args=[self.vecino.pk]))
        self.assertEqual(respuesta.status_code, 403)


# ============================================================
# MEMBRESÍA Y DIRIGENCIA EN JUNTAS DE VECINOS
# ============================================================

class PruebasMembresias(BaseComunidad):

    def setUp(self):
        self.vecino_2 = Vecino.objects.create(
            rut="11111111-1", nombre="Juan Soto", telefono="987654321", delegacion=self.centro,
        )

    def test_cp_mem_001_supervisor_agrega_socio(self):
        self.entrar(self.supervisor)
        respuesta = self.client.post(
            reverse("comunidad:membresia_crear", args=[self.junta.pk]),
            {"vecino": self.vecino.pk, "tipo": "SOCIO", "cargo": "", "fecha_inicio": "2026-01-10"},
        )
        self.assertRedirects(respuesta, reverse("comunidad:membresia_lista", args=[self.junta.pk]))
        self.assertTrue(MembresiaJunta.objects.filter(vecino=self.vecino, organizacion=self.junta, activo=True).exists())

    def test_cp_mem_002_dirigente_requiere_cargo(self):
        membresia = MembresiaJunta(vecino=self.vecino, organizacion=self.junta, tipo="DIRIGENTE")
        with self.assertRaises(ValidationError) as error:
            membresia.full_clean()
        self.assertIn("cargo", error.exception.message_dict)

    def test_cp_mem_003_presidente_es_unico(self):
        MembresiaJunta.objects.create(vecino=self.vecino, organizacion=self.junta, tipo="DIRIGENTE", cargo="PRESIDENTE")
        otro = MembresiaJunta(vecino=self.vecino_2, organizacion=self.junta, tipo="DIRIGENTE", cargo="PRESIDENTE")
        with self.assertRaises(ValidationError) as error:
            otro.full_clean()
        self.assertIn("cargo", error.exception.message_dict)

    def test_cp_mem_004_directores_pueden_ser_varios(self):
        MembresiaJunta.objects.create(vecino=self.vecino, organizacion=self.junta, tipo="DIRIGENTE", cargo="DIRECTOR")
        MembresiaJunta(vecino=self.vecino_2, organizacion=self.junta, tipo="DIRIGENTE", cargo="DIRECTOR").full_clean()

    def test_cp_mem_005_no_duplica_membresia_vigente(self):
        MembresiaJunta.objects.create(vecino=self.vecino, organizacion=self.junta)
        with self.assertRaises(ValidationError):
            MembresiaJunta(vecino=self.vecino, organizacion=self.junta).full_clean()

    def test_cp_mem_006_vecino_de_otra_delegacion_se_rechaza(self):
        ajeno = Vecino.objects.create(rut="22222222-2", nombre="Ana", telefono="911111111", delegacion=self.pampa)
        with self.assertRaises(ValidationError) as error:
            MembresiaJunta(vecino=ajeno, organizacion=self.junta).full_clean()
        self.assertIn("vecino", error.exception.message_dict)

    def test_cp_mem_007_cerrar_membresia_la_deja_en_historial(self):
        membresia = MembresiaJunta.objects.create(
            vecino=self.vecino, organizacion=self.junta, tipo="DIRIGENTE", cargo="PRESIDENTE",
            fecha_inicio=date.today() - timedelta(days=30),
        )
        self.entrar(self.supervisor)
        self.client.post(reverse("comunidad:membresia_cerrar", args=[membresia.pk]))
        membresia.refresh_from_db()
        self.assertFalse(membresia.activo)
        self.assertEqual(membresia.fecha_termino, date.today())
        # El cargo queda libre para el nuevo presidente.
        MembresiaJunta(vecino=self.vecino_2, organizacion=self.junta, tipo="DIRIGENTE", cargo="PRESIDENTE").full_clean()

    def test_cp_mem_008_termino_anterior_al_inicio_se_rechaza(self):
        membresia = MembresiaJunta(
            vecino=self.vecino, organizacion=self.junta,
            fecha_inicio=date(2026, 5, 1), fecha_termino=date(2026, 4, 1),
        )
        with self.assertRaises(ValidationError) as error:
            membresia.full_clean()
        self.assertIn("fecha_termino", error.exception.message_dict)

    def test_cp_mem_009_socio_no_guarda_cargo(self):
        membresia = MembresiaJunta.objects.create(
            vecino=self.vecino, organizacion=self.junta, tipo="SOCIO", cargo="TESORERO",
        )
        self.assertEqual(membresia.cargo, "")

    def test_cp_mem_010_listado_separa_directiva_y_socios(self):
        MembresiaJunta.objects.create(vecino=self.vecino, organizacion=self.junta, tipo="DIRIGENTE", cargo="TESORERO")
        MembresiaJunta.objects.create(vecino=self.vecino_2, organizacion=self.junta, tipo="SOCIO")
        self.entrar(self.administrativo)
        respuesta = self.client.get(reverse("comunidad:membresia_lista", args=[self.junta.pk]))
        self.assertEqual(list(respuesta.context["directiva"].values_list("vecino__nombre", flat=True)), ["María Pérez"])
        self.assertEqual(list(respuesta.context["socios"].values_list("vecino__nombre", flat=True)), ["Juan Soto"])

    def test_cp_mem_011_administrativo_no_agrega_membresias(self):
        self.entrar(self.administrativo)
        respuesta = self.client.get(reverse("comunidad:membresia_crear", args=[self.junta.pk]))
        self.assertEqual(respuesta.status_code, 403)

    def test_cp_mem_012_organizacion_de_otra_delegacion_responde_403(self):
        self.entrar(self.supervisor_pampa)
        respuesta = self.client.get(reverse("comunidad:membresia_lista", args=[self.junta.pk]))
        self.assertEqual(respuesta.status_code, 403)

    def test_cp_mem_013_organizaciones_muestran_enlace_a_socios(self):
        self.entrar(self.supervisor)
        respuesta = self.client.get(reverse("organizaciones:organizacion_lista"))
        self.assertContains(respuesta, reverse("comunidad:membresia_lista", args=[self.junta.pk]))


# ============================================================
# HITOS
# ============================================================

class PruebasHitos(BaseComunidad):

    def datos(self, **cambios):
        datos = {
            "nombre": "Operativo de salud", "descripcion": "", "delegacion": self.centro.pk,
            "territorio": self.territorio.pk, "organizacion": self.junta.pk,
            "responsable": self.administrativo.pk,
            "fecha_programada": (date.today() + timedelta(days=7)).isoformat(),
            "estado": "PENDIENTE", "fecha_cumplimiento": "",
        }
        datos.update(cambios)
        return datos

    def test_cp_hit_001_supervisor_crea_hito_con_responsable(self):
        self.entrar(self.supervisor)
        respuesta = self.client.post(reverse("comunidad:hito_crear"), self.datos())
        self.assertRedirects(respuesta, reverse("comunidad:hito_lista"))
        hito = Hito.objects.get(nombre="Operativo de salud")
        self.assertEqual(hito.responsable, self.administrativo)
        self.assertEqual(hito.creado_por, self.supervisor)

    def test_cp_hit_002_responsable_debe_ser_de_la_delegacion(self):
        hito = Hito(
            nombre="X", delegacion=self.centro, responsable=self.supervisor_pampa,
            fecha_programada=date.today(),
        )
        with self.assertRaises(ValidationError) as error:
            hito.full_clean()
        self.assertIn("responsable", error.exception.message_dict)

    def test_cp_hit_003_cumplido_exige_fecha_de_cumplimiento(self):
        hito = Hito(
            nombre="X", delegacion=self.centro, responsable=self.administrativo,
            fecha_programada=date.today(), estado=Hito.CUMPLIDO,
        )
        with self.assertRaises(ValidationError) as error:
            hito.full_clean()
        self.assertIn("fecha_cumplimiento", error.exception.message_dict)

    def test_cp_hit_004_fecha_de_cumplimiento_no_puede_ser_futura(self):
        hito = Hito(
            nombre="X", delegacion=self.centro, responsable=self.administrativo,
            fecha_programada=date.today(), estado=Hito.CUMPLIDO,
            fecha_cumplimiento=date.today() + timedelta(days=1),
        )
        with self.assertRaises(ValidationError):
            hito.full_clean()

    def test_cp_hit_005_territorio_de_otra_delegacion_se_rechaza(self):
        hito = Hito(
            nombre="X", delegacion=self.centro, territorio=self.territorio_pampa,
            responsable=self.administrativo, fecha_programada=date.today(),
        )
        with self.assertRaises(ValidationError) as error:
            hito.full_clean()
        self.assertIn("territorio", error.exception.message_dict)

    def test_cp_hit_006_filtro_atrasados(self):
        Hito.objects.create(
            nombre="Vencido", delegacion=self.centro, responsable=self.administrativo,
            fecha_programada=date.today() - timedelta(days=3),
        )
        Hito.objects.create(
            nombre="Futuro", delegacion=self.centro, responsable=self.administrativo,
            fecha_programada=date.today() + timedelta(days=3),
        )
        self.entrar(self.supervisor)
        respuesta = self.client.get(reverse("comunidad:hito_lista"), {"situacion": "atrasados"})
        self.assertContains(respuesta, "Vencido")
        self.assertNotContains(respuesta, "Futuro")

    def test_cp_hit_007_filtro_a_mi_cargo_y_rango_de_fechas(self):
        Hito.objects.create(
            nombre="Mío", delegacion=self.centro, responsable=self.administrativo,
            fecha_programada=date(2026, 11, 10),
        )
        Hito.objects.create(
            nombre="Del delegado", delegacion=self.centro, responsable=self.supervisor,
            fecha_programada=date(2026, 11, 10),
        )
        self.entrar(self.administrativo)
        respuesta = self.client.get(reverse("comunidad:hito_lista"), {
            "responsable": "yo", "desde": "2026-11-01", "hasta": "2026-11-30",
        })
        self.assertContains(respuesta, "Mío")
        self.assertNotContains(respuesta, "Del delegado")

    def test_cp_hit_008_listado_respeta_ambito(self):
        Hito.objects.create(
            nombre="Hito Pampa", delegacion=self.pampa, responsable=self.supervisor_pampa,
            fecha_programada=date.today(),
        )
        self.entrar(self.supervisor)
        self.assertNotContains(self.client.get(reverse("comunidad:hito_lista")), "Hito Pampa")

    def test_cp_hit_009_administrativo_consulta_pero_no_crea(self):
        self.entrar(self.administrativo)
        self.assertEqual(self.client.get(reverse("comunidad:hito_lista")).status_code, 200)
        self.assertEqual(self.client.get(reverse("comunidad:hito_crear")).status_code, 403)

    def test_cp_hit_010_baja_logica(self):
        hito = Hito.objects.create(
            nombre="Baja", delegacion=self.centro, responsable=self.administrativo,
            fecha_programada=date.today(),
        )
        self.entrar(self.supervisor)
        self.client.post(reverse("comunidad:hito_cambiar_estado", args=[hito.pk]))
        hito.refresh_from_db()
        self.assertFalse(hito.activo)
        self.assertTrue(Hito.objects.filter(pk=hito.pk).exists())

    def test_cp_hit_011_fecha_invalida_en_filtro_no_rompe(self):
        self.entrar(self.supervisor)
        respuesta = self.client.get(reverse("comunidad:hito_lista"), {"desde": "no-es-fecha"})
        self.assertEqual(respuesta.status_code, 200)


class PruebasMenu(BaseComunidad):

    def test_cp_ter_011_menu_muestra_las_nuevas_secciones_segun_permisos(self):
        self.entrar(self.supervisor)
        respuesta = self.client.get(reverse("comunidad:vecino_lista"))
        for nombre in ("territorio_lista", "vecino_lista", "hito_lista"):
            self.assertContains(respuesta, reverse(f"comunidad:{nombre}"))

    def test_cp_ter_012_sin_sesion_redirige_al_login(self):
        for nombre in ("territorio_lista", "vecino_lista", "hito_lista"):
            respuesta = self.client.get(reverse(f"comunidad:{nombre}"))
            self.assertEqual(respuesta.status_code, 302)
