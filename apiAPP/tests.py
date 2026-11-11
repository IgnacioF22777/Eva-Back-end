from decimal import Decimal

from rest_framework.test import APITestCase

from delegacionesAPP.models import Delegacion, Servicio
from seguridadAPP.models import Cargo
from seguridadAPP.perfiles import ADMINISTRADOR, ADMINISTRATIVO, SUPERVISOR
from seguridadAPP.roles import sincronizar_roles
from sgr_maestrosAPP.models import CatalogoActividad, Meta, Periodo
from tubo_gestionAPP.models import Compromiso
from tubo_gestionAPP.tests import CLAVE, crear_usuario


def crear_delegacion(nombre):
    # Todos los campos con datos válidos: la API valida el registro
    # completo con el formulario web, donde el celular es obligatorio.
    return Delegacion.objects.create(
        nombre=nombre,
        direccion="Dirección de prueba",
        encargado="Encargado",
        email=f"{nombre.split()[-1].lower()}@laserena.cl",
        telefono="51 2 000 000",
        celular="+56 9 1111 1111",
    )


# ============================================================
# PRUEBAS DE LA API RESTFUL (apiAPP)
# ============================================================
# Los ID CP-API-### permiten registrar el resultado esperado y el
# obtenido en la matriz de pruebas del informe.


class BaseAPI(APITestCase):

    @classmethod
    def setUpTestData(cls):
        sincronizar_roles()

        cls.centro = crear_delegacion("Delegación Centro")
        cls.rural = crear_delegacion("Delegación Rural")

        cls.admin = crear_usuario(
            "11.111.111-1", "admin@laserena.cl", ADMINISTRADOR
        )
        cls.supervisor = crear_usuario(
            "12.345.678-5", "sup@laserena.cl", SUPERVISOR,
            delegacion=cls.centro,
        )
        cls.administrativo_centro = crear_usuario(
            "22.222.222-2", "adm.centro@laserena.cl", ADMINISTRATIVO,
            delegacion=cls.centro,
        )
        cls.administrativo_rural = crear_usuario(
            "15.555.555-5", "adm.rural@laserena.cl", ADMINISTRATIVO,
            delegacion=cls.rural,
        )

    def como(self, usuario):
        self.client.force_authenticate(user=usuario)


# ============================================================
# AUTENTICACIÓN JWT
# ============================================================

class PruebasAutenticacionJWT(BaseAPI):

    def pedir_token(self, username, password=CLAVE):
        return self.client.post(
            "/api/token/",
            {"username": username, "password": password},
            format="json",
        )

    def usar_token(self, token):
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    def test_cp_api_001_sin_token_responde_401(self):
        respuesta = self.client.get("/api/delegaciones/")
        self.assertEqual(respuesta.status_code, 401)

    def test_cp_api_002_token_con_rut_con_puntos(self):
        respuesta = self.pedir_token("22.222.222-2")

        self.assertEqual(respuesta.status_code, 200)
        self.assertIn("access", respuesta.data)
        self.assertIn("refresh", respuesta.data)

        self.usar_token(respuesta.data["access"])
        self.assertEqual(self.client.get("/api/delegaciones/").status_code, 200)

    def test_cp_api_003_token_con_correo(self):
        respuesta = self.pedir_token("adm.centro@laserena.cl")
        self.assertEqual(respuesta.status_code, 200)

    def test_cp_api_004_clave_incorrecta_responde_401(self):
        respuesta = self.pedir_token("22.222.222-2", "otra-clave")
        self.assertEqual(respuesta.status_code, 401)
        self.assertNotIn("access", respuesta.data)

    def test_cp_api_005_bloqueo_tras_5_intentos(self):
        # Borde: el 5.º fallo todavía responde 401; desde el 6.º intento,
        # incluso con la clave correcta, responde 429.
        for _ in range(5):
            self.assertEqual(
                self.pedir_token("22.222.222-2", "mala").status_code, 401
            )

        respuesta = self.pedir_token("22.222.222-2")
        self.assertEqual(respuesta.status_code, 429)

        # El bloqueo se comparte con el login web: misma clave de RUT
        # aunque se escriba sin puntos.
        self.assertEqual(self.pedir_token("22222222-2").status_code, 429)

    def test_cp_api_006_ingreso_correcto_reinicia_contador(self):
        for _ in range(4):
            self.pedir_token("22.222.222-2", "mala")

        self.assertEqual(self.pedir_token("22.222.222-2").status_code, 200)
        self.assertEqual(
            self.pedir_token("22.222.222-2", "mala").status_code, 401
        )
        self.assertEqual(self.pedir_token("22.222.222-2").status_code, 200)

    def test_cp_api_007_usuario_desactivado_pierde_acceso(self):
        token = self.pedir_token("22.222.222-2").data["access"]

        self.administrativo_centro.is_active = False
        self.administrativo_centro.save()

        self.usar_token(token)
        self.assertEqual(self.client.get("/api/delegaciones/").status_code, 401)

    def test_cp_api_008_cambio_de_clave_invalida_tokens(self):
        token = self.pedir_token("22.222.222-2").data["access"]

        self.administrativo_centro.set_password("NuevaClave#2026")
        self.administrativo_centro.save()

        self.usar_token(token)
        self.assertEqual(self.client.get("/api/delegaciones/").status_code, 401)

    def test_cp_api_009_refresh_entrega_nuevo_access(self):
        refresh = self.pedir_token("22.222.222-2").data["refresh"]

        respuesta = self.client.post(
            "/api/token/refresh/", {"refresh": refresh}, format="json"
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertIn("access", respuesta.data)

    def test_cp_api_010_token_manipulado_responde_401(self):
        token = self.pedir_token("22.222.222-2").data["access"]
        self.usar_token(token[:-2] + "xx")

        self.assertEqual(self.client.get("/api/delegaciones/").status_code, 401)

    def test_usuario_actual_muestra_perfil_y_delegacion(self):
        self.como(self.supervisor)

        respuesta = self.client.get("/api/yo/")

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.data["perfil"], SUPERVISOR)
        self.assertEqual(respuesta.data["delegacion"], "Delegación Centro")
        self.assertEqual(respuesta.data["rut"], "12.345.678-5")


# ============================================================
# PERMISOS POR PERFIL
# ============================================================

class PruebasPermisos(BaseAPI):

    def test_cp_api_011_administrativo_consulta_pero_no_crea(self):
        self.como(self.administrativo_centro)

        self.assertEqual(self.client.get("/api/delegaciones/").status_code, 200)

        respuesta = self.client.post(
            "/api/delegaciones/", {"nombre": "Nueva"}, format="json"
        )
        self.assertEqual(respuesta.status_code, 403)
        self.assertFalse(Delegacion.objects.filter(nombre="Nueva").exists())

    def test_cp_api_012_supervisor_no_elimina_periodos(self):
        periodo = Periodo.objects.create(
            codigo="P1", nombre="P1",
            fecha_inicio="2026-01-01", fecha_fin="2026-03-31",
        )
        self.como(self.supervisor)

        respuesta = self.client.delete(f"/api/periodos/{periodo.pk}/")

        self.assertEqual(respuesta.status_code, 403)
        self.assertTrue(Periodo.objects.filter(pk=periodo.pk).exists())

    def test_cp_api_013_administrativo_no_modifica_catalogo(self):
        actividad = CatalogoActividad.objects.create(codigo="A1", nombre="A")
        self.como(self.administrativo_centro)

        respuesta = self.client.patch(
            f"/api/catalogo/{actividad.pk}/", {"nombre": "Otro"}, format="json"
        )

        self.assertEqual(respuesta.status_code, 403)

    def test_documentacion_swagger_disponible(self):
        self.assertEqual(self.client.get("/api/schema/").status_code, 200)
        self.assertEqual(self.client.get("/api/swagger/").status_code, 200)
        self.assertEqual(self.client.get("/api/redoc/").status_code, 200)


# ============================================================
# DELEGACIONES Y SERVICIOS
# ============================================================

class PruebasDelegaciones(BaseAPI):

    DATOS = {
        "nombre": "Delegación Las Compañías",
        "direccion": "Av. Las Compañías 1234",
        "encargado": "María Pérez",
        "email": "COMPANIAS@LaSerena.cl",
        "telefono": "51 2 000 000",
        "celular": "+56 9 1234 5678",
    }

    def setUp(self):
        self.como(self.admin)

    def test_cp_api_014_crear_delegacion(self):
        respuesta = self.client.post("/api/delegaciones/", self.DATOS, format="json")

        self.assertEqual(respuesta.status_code, 201)
        self.assertTrue(respuesta.data["activo"])
        # El correo se normaliza igual que en la web.
        self.assertEqual(respuesta.data["email"], "companias@laserena.cl")

    def test_cp_api_015_nombre_duplicado_se_rechaza(self):
        datos = dict(self.DATOS, nombre="delegación centro")

        respuesta = self.client.post("/api/delegaciones/", datos, format="json")

        self.assertEqual(respuesta.status_code, 400)
        self.assertIn("nombre", respuesta.data)

    def test_cp_api_016_nombre_de_inactiva_la_reactiva(self):
        inactiva = crear_delegacion("Delegación Antigua")
        inactiva.activo = False
        inactiva.save()
        total = Delegacion.objects.count()

        datos = dict(self.DATOS, nombre="Delegación Antigua")
        respuesta = self.client.post("/api/delegaciones/", datos, format="json")

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.data["id"], inactiva.pk)
        self.assertTrue(respuesta.data["activo"])
        self.assertEqual(Delegacion.objects.count(), total)

    def test_cp_api_017_baja_bloqueada_con_servicios_activos(self):
        Servicio.objects.create(delegacion=self.centro, nombre="Aseo")

        respuesta = self.client.delete(f"/api/delegaciones/{self.centro.pk}/")

        self.assertEqual(respuesta.status_code, 409)
        self.centro.refresh_from_db()
        self.assertTrue(self.centro.activo)

    def test_cp_api_018_baja_logica_y_reactivacion(self):
        url = f"/api/delegaciones/{self.rural.pk}/"

        respuesta = self.client.delete(url)
        self.assertEqual(respuesta.status_code, 200)
        self.assertFalse(respuesta.data["activo"])

        # No se borra: sigue en la base y aparece en "inactivos".
        self.assertTrue(Delegacion.objects.filter(pk=self.rural.pk).exists())
        activos = [d["id"] for d in self.client.get("/api/delegaciones/").data]
        inactivos = [
            d["id"]
            for d in self.client.get("/api/delegaciones/?estado=inactivos").data
        ]
        self.assertNotIn(self.rural.pk, activos)
        self.assertIn(self.rural.pk, inactivos)

        respuesta = self.client.post(f"{url}reactivar/")
        self.assertEqual(respuesta.status_code, 200)
        self.assertTrue(respuesta.data["activo"])

    def test_cp_api_019_modificar_parcial(self):
        respuesta = self.client.patch(
            f"/api/delegaciones/{self.centro.pk}/",
            {"encargado": "  Juan Soto  "},
            format="json",
        )

        self.assertEqual(respuesta.status_code, 200)
        self.centro.refresh_from_db()
        self.assertEqual(self.centro.encargado, "Juan Soto")
        self.assertEqual(self.centro.nombre, "Delegación Centro")

    def test_cp_api_020_no_se_puede_activar_por_put(self):
        self.rural.activo = False
        self.rural.save()

        respuesta = self.client.patch(
            f"/api/delegaciones/{self.rural.pk}/",
            {"activo": True},
            format="json",
        )

        self.assertEqual(respuesta.status_code, 200)
        self.rural.refresh_from_db()
        self.assertFalse(self.rural.activo)

    def test_campo_obligatorio_vacio_se_rechaza(self):
        datos = dict(self.DATOS, celular="")

        respuesta = self.client.post("/api/delegaciones/", datos, format="json")

        self.assertEqual(respuesta.status_code, 400)
        self.assertIn("celular", respuesta.data)

    def test_registro_inexistente_responde_404(self):
        respuesta = self.client.get("/api/delegaciones/999999/")
        self.assertEqual(respuesta.status_code, 404)

    def test_buscar_delegacion(self):
        respuesta = self.client.get("/api/delegaciones/?q=rural")
        self.assertEqual([d["id"] for d in respuesta.data], [self.rural.pk])

    def test_cp_api_021_servicio_en_delegacion_inactiva_se_rechaza(self):
        self.rural.activo = False
        self.rural.save()

        respuesta = self.client.post(
            "/api/servicios/",
            {"delegacion": self.rural.pk, "nombre": "Riego"},
            format="json",
        )

        self.assertEqual(respuesta.status_code, 400)
        self.assertIn("delegacion", respuesta.data)

    def test_cp_api_022_servicio_no_cambia_de_delegacion(self):
        servicio = Servicio.objects.create(delegacion=self.centro, nombre="Aseo")

        respuesta = self.client.put(
            f"/api/servicios/{servicio.pk}/",
            {"delegacion": self.rural.pk, "nombre": "Aseo"},
            format="json",
        )

        self.assertEqual(respuesta.status_code, 400)
        servicio.refresh_from_db()
        self.assertEqual(servicio.delegacion, self.centro)

    def test_servicio_duplicado_activo_se_rechaza(self):
        Servicio.objects.create(delegacion=self.centro, nombre="Aseo")

        respuesta = self.client.post(
            "/api/servicios/",
            {"delegacion": self.centro.pk, "nombre": "ASEO"},
            format="json",
        )

        self.assertEqual(respuesta.status_code, 400)


# ============================================================
# COMPROMISOS: ÁMBITO POR DELEGACIÓN Y CAMPOS PROTEGIDOS
# ============================================================

class PruebasCompromisos(BaseAPI):

    def setUp(self):
        self.compromiso_centro = Compromiso.objects.create(
            tarea="Luminarias del centro", delegacion=self.centro,
            cumplimiento=60,
        )
        self.compromiso_rural = Compromiso.objects.create(
            tarea="Riego rural", delegacion=self.rural, cumplimiento=95,
        )

    def test_cp_api_023_administrativo_solo_ve_su_delegacion(self):
        self.como(self.administrativo_rural)

        ids = [c["id"] for c in self.client.get("/api/compromisos/").data]

        self.assertEqual(ids, [self.compromiso_rural.pk])

    def test_cp_api_024_compromiso_de_otra_delegacion_responde_403(self):
        self.como(self.administrativo_rural)

        respuesta = self.client.get(
            f"/api/compromisos/{self.compromiso_centro.pk}/"
        )

        self.assertEqual(respuesta.status_code, 403)

    def test_cp_api_025_cumplimiento_no_se_edita_por_la_api(self):
        self.como(self.admin)

        respuesta = self.client.patch(
            f"/api/compromisos/{self.compromiso_centro.pk}/",
            {"tarea": "Luminarias", "cumplimiento": 100, "estado": "verde"},
            format="json",
        )

        self.assertEqual(respuesta.status_code, 200)
        self.compromiso_centro.refresh_from_db()
        self.assertEqual(self.compromiso_centro.tarea, "Luminarias")
        self.assertEqual(self.compromiso_centro.cumplimiento, 60)
        self.assertEqual(self.compromiso_centro.estado, "amarillo")

    def test_cp_api_026_nuevo_compromiso_parte_en_rojo(self):
        self.como(self.supervisor)

        respuesta = self.client.post(
            "/api/compromisos/",
            {"tarea": "Reparar plaza", "cumplimiento": 90},
            format="json",
        )

        self.assertEqual(respuesta.status_code, 201)
        self.assertEqual(respuesta.data["cumplimiento"], 0)
        self.assertEqual(respuesta.data["estado"], "rojo")
        self.assertIsNone(respuesta.data["delegacion"])

    def test_tarea_vacia_se_rechaza(self):
        self.como(self.admin)

        respuesta = self.client.post(
            "/api/compromisos/", {"tarea": "   "}, format="json"
        )

        self.assertEqual(respuesta.status_code, 400)

    def test_filtro_por_semaforo(self):
        self.como(self.admin)

        respuesta = self.client.get("/api/compromisos/?semaforo=verde")

        self.assertEqual(
            [c["id"] for c in respuesta.data], [self.compromiso_rural.pk]
        )

    def test_baja_de_compromiso_fuera_de_ambito_responde_403(self):
        self.como(self.supervisor)

        respuesta = self.client.delete(
            f"/api/compromisos/{self.compromiso_rural.pk}/"
        )

        self.assertEqual(respuesta.status_code, 403)
        self.compromiso_rural.refresh_from_db()
        self.assertTrue(self.compromiso_rural.activo)


# ============================================================
# CATÁLOGO, PERÍODOS Y METAS (REGLAS DE LA EVALUACIÓN 3)
# ============================================================

class PruebasMaestros(BaseAPI):

    def setUp(self):
        self.como(self.admin)
        self.actividad = CatalogoActividad.objects.create(
            codigo="VISITA", nombre="Visita a terreno"
        )
        self.periodo = Periodo.objects.create(
            codigo="2026-T3", nombre="Tercer trimestre",
            fecha_inicio="2026-07-01", fecha_fin="2026-09-30",
        )
        self.cargo = Cargo.objects.create(nombre="Gestor Social")

    def crear_meta(self, codigo, ponderacion, cargo=None):
        return Meta.objects.create(
            codigo=codigo, nombre=codigo, periodo=self.periodo,
            actividad=self.actividad, cargo=cargo,
            valor_objetivo=Decimal("10"), ponderacion=Decimal(ponderacion),
        )

    def datos_meta(self, **cambios):
        datos = {
            "codigo": "META-API",
            "nombre": "Meta por API",
            "periodo": self.periodo.pk,
            "actividad": self.actividad.pk,
            "cargo": self.cargo.pk,
            "valor_objetivo": "12.00",
            "ponderacion": "20.00",
        }
        datos.update(cambios)
        return datos

    def test_cp_api_027_actividad_sin_tipo_queda_ejecucion(self):
        respuesta = self.client.post(
            "/api/catalogo/",
            {"codigo": "taller-01", "nombre": "Realización de taller"},
            format="json",
        )

        self.assertEqual(respuesta.status_code, 201)
        self.assertEqual(respuesta.data["codigo"], "TALLER-01")
        self.assertEqual(respuesta.data["tipo_gestion"], "EJECUCION")
        self.assertTrue(respuesta.data["puntua"])
        self.assertTrue(respuesta.data["activo"])

    def test_cp_api_028_actividad_preparatoria_no_puntua(self):
        respuesta = self.client.post(
            "/api/catalogo/",
            {
                "codigo": "COORD",
                "nombre": "Coordinación de taller",
                "tipo_gestion": "PREPARATORIA",
            },
            format="json",
        )

        self.assertEqual(respuesta.status_code, 201)
        self.assertFalse(respuesta.data["puntua"])

    def test_cp_api_029_tipo_invalido_y_codigo_duplicado(self):
        tipo_invalido = self.client.post(
            "/api/catalogo/",
            {"codigo": "X1", "nombre": "X", "tipo_gestion": "ejecucion"},
            format="json",
        )
        duplicado = self.client.post(
            "/api/catalogo/",
            {"codigo": "visita", "nombre": "Otra visita"},
            format="json",
        )

        self.assertEqual(tipo_invalido.status_code, 400)
        self.assertIn("tipo_gestion", tipo_invalido.data)
        self.assertEqual(duplicado.status_code, 400)
        self.assertIn("codigo", duplicado.data)

    def test_cp_api_030_actividad_con_metas_activas_no_se_da_de_baja(self):
        self.crear_meta("M1", "50")

        respuesta = self.client.delete(f"/api/catalogo/{self.actividad.pk}/")

        self.assertEqual(respuesta.status_code, 409)
        self.actividad.refresh_from_db()
        self.assertTrue(self.actividad.activo)

    def test_cp_api_031_meta_que_supera_100_del_cargo_se_rechaza(self):
        self.crear_meta("M1", "90", cargo=self.cargo)

        respuesta = self.client.post(
            "/api/metas/", self.datos_meta(ponderacion="10.01"), format="json"
        )

        self.assertEqual(respuesta.status_code, 400)
        self.assertIn("ponderacion", respuesta.data)
        self.assertIn("10", str(respuesta.data["ponderacion"]))

        # Borde: el valor exacto disponible se acepta.
        respuesta = self.client.post(
            "/api/metas/", self.datos_meta(ponderacion="10.00"), format="json"
        )
        self.assertEqual(respuesta.status_code, 201)

    def test_cp_api_032_cerrar_periodo_requiere_100_por_cargo(self):
        self.crear_meta("M1", "85", cargo=self.cargo)
        url = f"/api/periodos/{self.periodo.pk}/"

        respuesta = self.client.patch(url, {"cerrado": True}, format="json")
        self.assertEqual(respuesta.status_code, 400)
        self.assertIn("Gestor Social", str(respuesta.data))

        self.crear_meta("M2", "15", cargo=self.cargo)
        respuesta = self.client.patch(url, {"cerrado": True}, format="json")
        self.assertEqual(respuesta.status_code, 200)
        self.assertTrue(respuesta.data["cerrado"])

    def test_cp_api_033_periodo_cerrado_no_se_modifica(self):
        self.crear_meta("M1", "100", cargo=self.cargo)
        self.periodo.cerrado = True
        self.periodo.save()

        respuesta = self.client.patch(
            f"/api/periodos/{self.periodo.pk}/", {"nombre": "Otro"},
            format="json",
        )
        meta_nueva = self.client.post(
            "/api/metas/", self.datos_meta(ponderacion="0"), format="json"
        )

        self.assertEqual(respuesta.status_code, 409)
        self.assertEqual(meta_nueva.status_code, 400)
        self.assertIn("periodo", meta_nueva.data)

    def test_cp_api_034_periodo_con_metas_no_se_elimina(self):
        self.crear_meta("M1", "50")
        vacio = Periodo.objects.create(
            codigo="VACIO", nombre="Sin metas",
            fecha_inicio="2026-10-01", fecha_fin="2026-12-31",
        )

        con_metas = self.client.delete(f"/api/periodos/{self.periodo.pk}/")
        sin_metas = self.client.delete(f"/api/periodos/{vacio.pk}/")

        self.assertEqual(con_metas.status_code, 409)
        self.assertEqual(sin_metas.status_code, 204)
        self.assertFalse(Periodo.objects.filter(pk=vacio.pk).exists())

    def test_cp_api_035_reactivar_meta_que_superaria_100_se_rechaza(self):
        inactiva = self.crear_meta("M1", "40", cargo=self.cargo)
        inactiva.activo = False
        inactiva.save()
        self.crear_meta("M2", "70", cargo=self.cargo)

        respuesta = self.client.post(f"/api/metas/{inactiva.pk}/reactivar/")

        self.assertEqual(respuesta.status_code, 409)
        inactiva.refresh_from_db()
        self.assertFalse(inactiva.activo)

    def test_periodo_con_fechas_invertidas_se_rechaza(self):
        respuesta = self.client.post(
            "/api/periodos/",
            {
                "codigo": "MAL",
                "nombre": "Mal",
                "fecha_inicio": "2026-12-31",
                "fecha_fin": "2026-01-01",
            },
            format="json",
        )

        self.assertEqual(respuesta.status_code, 400)
        self.assertIn("fecha_fin", respuesta.data)

    def test_periodo_muestra_suma_por_cargo(self):
        self.crear_meta("M1", "60", cargo=self.cargo)

        respuesta = self.client.get(f"/api/periodos/{self.periodo.pk}/")

        resumen = respuesta.data["ponderaciones_por_cargo"]
        self.assertEqual(resumen[0]["cargo"], "Gestor Social")
        self.assertEqual(Decimal(resumen[0]["suma"]), Decimal("60"))
        self.assertFalse(resumen[0]["completo"])

    def test_filtro_metas_por_cargo(self):
        general = self.crear_meta("GENERAL", "10")
        del_cargo = self.crear_meta("CARGO", "10", cargo=self.cargo)

        sin = self.client.get("/api/metas/?cargo=sin").data
        con = self.client.get(f"/api/metas/?cargo={self.cargo.pk}").data

        self.assertEqual([m["id"] for m in sin], [general.pk])
        self.assertEqual([m["id"] for m in con], [del_cargo.pk])
