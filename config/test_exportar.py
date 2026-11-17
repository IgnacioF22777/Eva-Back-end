"""
Pruebas de la exportación de listados a Excel (openpyxl) y PDF (ReportLab).

Casos CP-EXP-001 a CP-EXP-016: permisos, contenido de los archivos, filtros
del listado, ámbito por delegación, registros propios, casos de borde
(listado vacío, textos con "<" o "=", muchas filas) y botones en pantalla.
"""

from datetime import date
from io import BytesIO

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone
from openpyxl import load_workbook
from reportlab.lib.pagesizes import letter

from actividadesAPP.models import RegistroActividad, ZONA_CHILE
from delegacionesAPP.models import Servicio
from seguridadAPP.models import Cargo, PerfilUsuario
from seguridadAPP.perfiles import ADMINISTRADOR, ADMINISTRATIVO
from seguridadAPP.roles import sincronizar_roles
from sgr_maestrosAPP.models import CatalogoActividad, Meta, Periodo
from tubo_gestionAPP.models import AsignacionCompromiso, Compromiso
from tubo_gestionAPP.test_ambito_y_adjuntos import crear_delegacion
from tubo_gestionAPP.tests import crear_usuario

from . import exportar


CONTENT_TYPE_EXCEL = exportar.CONTENT_TYPE_EXCEL
FILA_ENCABEZADOS = 4

# (ruta Excel, ruta PDF) de cada listado exportable.
RUTAS = [
    ("sgr_maestros:exportar_catalogo_excel", "sgr_maestros:exportar_catalogo_pdf"),
    ("sgr_maestros:exportar_periodos_excel", "sgr_maestros:exportar_periodos_pdf"),
    ("sgr_maestros:exportar_metas_excel", "sgr_maestros:exportar_metas_pdf"),
    ("exportar_compromisos_excel", "exportar_compromisos_pdf"),
    ("exportar_delegaciones_excel", "exportar_delegaciones_pdf"),
    ("actividades:exportar_excel", "actividades:exportar_pdf"),
]
TODAS_LAS_RUTAS = [ruta for par in RUTAS for ruta in par]


def leer_excel(respuesta):
    """Abre el .xlsx de la respuesta y devuelve la hoja activa."""
    return load_workbook(BytesIO(respuesta.content)).active


def filas_de_datos(hoja):
    """Valores de las filas bajo los encabezados."""
    return [
        list(fila)
        for fila in hoja.iter_rows(min_row=FILA_ENCABEZADOS + 1, values_only=True)
    ]


def columna(hoja, indice):
    return [fila[indice] for fila in filas_de_datos(hoja)]


class BaseExportacion(TestCase):
    """Datos de prueba de todos los listados exportables."""

    @classmethod
    def setUpTestData(cls):
        sincronizar_roles()

        cls.centro = crear_delegacion("Delegación Centro")
        cls.rural = crear_delegacion("Delegación Rural")
        cls.servicio_centro = Servicio.objects.create(
            delegacion=cls.centro, nombre="Aseo y ornato"
        )
        cls.servicio_rural = Servicio.objects.create(
            delegacion=cls.rural, nombre="Riego rural"
        )

        cls.admin = crear_usuario(
            "11.111.111-1", "admin@laserena.cl", ADMINISTRADOR
        )
        cls.administrativo_centro = crear_usuario(
            "22.222.222-2", "adm.centro@laserena.cl", ADMINISTRATIVO,
            delegacion=cls.centro,
        )
        cls.administrativo_rural = crear_usuario(
            "15.555.555-5", "adm.rural@laserena.cl", ADMINISTRATIVO,
            delegacion=cls.rural,
        )
        # Usuario sin perfil ni grupos: no tiene ningún permiso.
        cls.sin_permisos = get_user_model().objects.create_user(
            username="sinpermisos", password="ClaveSegura#2026"
        )

        cls.ejecucion = CatalogoActividad.objects.create(
            codigo="ACT-001", nombre="Atención presencial", area="Social",
        )
        cls.preparatoria = CatalogoActividad.objects.create(
            codigo="ACT-002", nombre="Coordinación de taller", area="Social",
            tipo_gestion="PREPARATORIA",
        )
        cls.inactiva = CatalogoActividad.objects.create(
            codigo="ACT-003", nombre="Actividad antigua", area="Social",
            activo=False,
        )

        cls.periodo = Periodo.objects.create(
            codigo="2026-T4", nombre="Cuarto trimestre 2026",
            fecha_inicio=date(2026, 10, 1), fecha_fin=date(2026, 12, 31),
        )
        cls.cargo = Cargo.objects.create(nombre="Gestor Social")
        Meta.objects.create(
            codigo="M-01", nombre="Atenciones del gestor", periodo=cls.periodo,
            actividad=cls.ejecucion, cargo=cls.cargo,
            valor_objetivo=90, ponderacion=100,
        )
        Meta.objects.create(
            codigo="M-02", nombre="Meta general", periodo=cls.periodo,
            actividad=cls.ejecucion, valor_objetivo=10, ponderacion=40,
        )

        cls.compromiso_centro = cls.crear_compromiso(
            "Luminarias del centro", cls.centro, cls.servicio_centro
        )
        cls.compromiso_rural = cls.crear_compromiso(
            "Riego de plazas rurales", cls.rural, cls.servicio_rural
        )

        hoy = timezone.localdate(timezone.now(), timezone=ZONA_CHILE)
        cls.registro_centro = RegistroActividad.objects.create(
            funcionario=cls.administrativo_centro.perfil,
            actividad=cls.ejecucion, fecha_actividad=hoy,
            nombre_usuario="Vecina del centro", telefono_usuario="912345678",
        )
        cls.registro_rural = RegistroActividad.objects.create(
            funcionario=cls.administrativo_rural.perfil,
            actividad=cls.ejecucion, fecha_actividad=hoy,
            nombre_usuario="Vecino rural", telefono_usuario="987654321",
        )

    @classmethod
    def crear_compromiso(cls, tarea, delegacion, servicio):
        compromiso = Compromiso.objects.create(
            tarea=tarea, cumplimiento=95,
            delegacion=delegacion, servicio=servicio,
        )
        AsignacionCompromiso.objects.create(
            compromiso=compromiso, delegacion=delegacion, servicio=servicio,
            usuario_asignador=cls.admin,
        )
        return compromiso


# ============================================================
# PERMISOS
# ============================================================

class PruebasPermisosExportacion(BaseExportacion):

    def test_cp_exp_001_sin_sesion_redirige_al_login(self):
        for ruta in TODAS_LAS_RUTAS:
            with self.subTest(ruta=ruta):
                respuesta = self.client.get(reverse(ruta))
                self.assertEqual(respuesta.status_code, 302)
                self.assertIn("/seguridad/login/", respuesta["Location"])

    def test_cp_exp_002_sin_permiso_responde_403(self):
        self.client.force_login(self.sin_permisos)
        for ruta in TODAS_LAS_RUTAS:
            with self.subTest(ruta=ruta):
                self.assertEqual(self.client.get(reverse(ruta)).status_code, 403)


# ============================================================
# ARCHIVOS GENERADOS
# ============================================================

class PruebasArchivosExportados(BaseExportacion):

    def setUp(self):
        self.client.force_login(self.administrativo_centro)

    def test_cp_exp_003_excel_valido_con_titulo_y_encabezados(self):
        for ruta, _ in RUTAS:
            with self.subTest(ruta=ruta):
                respuesta = self.client.get(reverse(ruta))
                self.assertEqual(respuesta.status_code, 200)
                self.assertEqual(respuesta["Content-Type"], CONTENT_TYPE_EXCEL)
                self.assertRegex(
                    respuesta["Content-Disposition"],
                    r'^attachment; filename="[a-z_]+_\d{8}_\d{4}\.xlsx"$',
                )
                hoja = leer_excel(respuesta)
                self.assertTrue(hoja["A1"].value)
                self.assertIn("Municipalidad de La Serena", hoja["A2"].value)
                self.assertIsNotNone(hoja.cell(FILA_ENCABEZADOS, 1).value)

    def test_cp_exp_004_pdf_valido(self):
        for _, ruta in RUTAS:
            with self.subTest(ruta=ruta):
                respuesta = self.client.get(reverse(ruta))
                self.assertEqual(respuesta.status_code, 200)
                self.assertEqual(respuesta["Content-Type"], "application/pdf")
                self.assertRegex(
                    respuesta["Content-Disposition"],
                    r'^attachment; filename="[a-z_]+_\d{8}_\d{4}\.pdf"$',
                )
                self.assertTrue(respuesta.content.startswith(b"%PDF"))
                self.assertIn(b"%%EOF", respuesta.content[-1024:])

    def test_cp_exp_005_catalogo_respeta_filtros(self):
        url = reverse("sgr_maestros:exportar_catalogo_excel")

        # Por defecto, igual que el listado: solo actividades activas.
        hoja = leer_excel(self.client.get(url))
        self.assertEqual(columna(hoja, 0), ["ACT-001", "ACT-002"])

        hoja = leer_excel(self.client.get(url, {"tipo": "PREPARATORIA"}))
        self.assertEqual(columna(hoja, 0), ["ACT-002"])
        self.assertEqual(
            filas_de_datos(hoja)[0][3], "Preparatoria (no suma puntaje)"
        )

        hoja = leer_excel(self.client.get(url, {"estado": "inactivos"}))
        self.assertEqual(columna(hoja, 0), ["ACT-003"])

        hoja = leer_excel(self.client.get(url, {"q": "taller", "estado": "todos"}))
        self.assertEqual(columna(hoja, 0), ["ACT-002"])

    def test_cp_exp_006_metas_filtran_por_cargo_y_conservan_numeros(self):
        url = reverse("sgr_maestros:exportar_metas_excel")

        hoja = leer_excel(self.client.get(url, {"cargo": "sin"}))
        self.assertEqual(columna(hoja, 0), ["M-02"])
        self.assertEqual(filas_de_datos(hoja)[0][3], "Sin cargo (general)")

        hoja = leer_excel(self.client.get(url, {"cargo": self.cargo.pk}))
        fila = filas_de_datos(hoja)[0]
        self.assertEqual(fila[0], "M-01")
        self.assertEqual(fila[3], "Gestor Social")
        # Valor objetivo y ponderación quedan como números, no como texto.
        self.assertEqual(fila[5], 90)
        self.assertEqual(fila[6], 100)

    def test_cp_exp_007_periodos_con_fechas_y_ponderacion_por_cargo(self):
        hoja = leer_excel(
            self.client.get(reverse("sgr_maestros:exportar_periodos_excel"))
        )
        fila = filas_de_datos(hoja)[0]
        self.assertEqual(fila[0], "2026-T4")
        self.assertEqual(fila[2].date(), date(2026, 10, 1))
        self.assertEqual(
            hoja.cell(FILA_ENCABEZADOS + 1, 3).number_format, "DD/MM/YYYY"
        )
        self.assertIn("Gestor Social: 100%", fila[6])
        self.assertIn("Sin cargo: 40% de 100%", fila[6])
        self.assertEqual(fila[7], "Abierto")

    def test_cp_exp_008_compromisos_respetan_ambito_por_delegacion(self):
        hoja = leer_excel(self.client.get(reverse("exportar_compromisos_excel")))
        tareas = columna(hoja, 1)
        self.assertIn("Luminarias del centro", tareas)
        self.assertNotIn("Riego de plazas rurales", tareas)

        # El Administrador ve todas las delegaciones.
        self.client.force_login(self.admin)
        hoja = leer_excel(self.client.get(reverse("exportar_compromisos_excel")))
        self.assertIn("Riego de plazas rurales", columna(hoja, 1))

    def test_cp_exp_009_actividades_solo_registros_propios(self):
        hoja = leer_excel(self.client.get(reverse("actividades:exportar_excel")))
        self.assertEqual(columna(hoja, 4), ["Vecina del centro"])
        self.assertNotIn("Vecino rural", columna(hoja, 4))
        self.assertEqual(filas_de_datos(hoja)[0][6], "Válida")

    def test_cp_exp_010_delegaciones_con_totales(self):
        hoja = leer_excel(self.client.get(reverse("exportar_delegaciones_excel")))
        filas = {fila[0]: fila for fila in filas_de_datos(hoja)}
        self.assertEqual(set(filas), {"Delegación Centro", "Delegación Rural"})
        self.assertEqual(filas["Delegación Centro"][6], 1)  # servicios activos
        self.assertEqual(filas["Delegación Centro"][7], 1)  # compromisos activos
        self.assertEqual(filas["Delegación Centro"][8], "Activa")


# ============================================================
# CASOS DE BORDE
# ============================================================

class PruebasBordeExportacion(BaseExportacion):

    def setUp(self):
        self.client.force_login(self.admin)

    def test_cp_exp_011_listado_vacio_genera_archivos_con_aviso(self):
        filtro = {"q": "no-existe-ningun-registro"}

        hoja = leer_excel(
            self.client.get(reverse("sgr_maestros:exportar_catalogo_excel"), filtro)
        )
        self.assertEqual(
            hoja.cell(FILA_ENCABEZADOS + 1, 1).value, exportar.SIN_REGISTROS
        )

        respuesta = self.client.get(
            reverse("sgr_maestros:exportar_catalogo_pdf"), filtro
        )
        self.assertEqual(respuesta.status_code, 200)
        self.assertTrue(respuesta.content.startswith(b"%PDF"))

    def test_cp_exp_012_texto_con_signo_igual_no_se_guarda_como_formula(self):
        CatalogoActividad.objects.create(
            codigo="ACT-099", nombre="=HYPERLINK(\"http://x\",\"clic\")",
            area="+cmd",
        )
        hoja = leer_excel(
            self.client.get(
                reverse("sgr_maestros:exportar_catalogo_excel"), {"q": "ACT-099"}
            )
        )
        celda = hoja.cell(FILA_ENCABEZADOS + 1, 2)
        self.assertEqual(celda.data_type, "s")
        self.assertEqual(celda.value, "=HYPERLINK(\"http://x\",\"clic\")")

    def test_cp_exp_013_pdf_con_caracteres_especiales(self):
        # "<" y "&" se escapan; sin escape, ReportLab fallaría al leer
        # el texto como etiquetas.
        CatalogoActividad.objects.create(
            codigo="ACT-100", nombre="Reunión <b>JJVV</b> & vecinos", area="Social",
        )
        respuesta = self.client.get(
            reverse("sgr_maestros:exportar_catalogo_pdf"), {"q": "ACT-100"}
        )
        self.assertEqual(respuesta.status_code, 200)
        self.assertTrue(respuesta.content.startswith(b"%PDF"))

    def test_cp_exp_014_muchas_filas_generan_varias_paginas(self):
        CatalogoActividad.objects.bulk_create(
            CatalogoActividad(
                codigo=f"MAS-{i:03d}", nombre=f"Actividad masiva {i}", area="Social"
            )
            for i in range(120)
        )
        respuesta = self.client.get(
            reverse("sgr_maestros:exportar_catalogo_pdf"), {"q": "MAS-"}
        )
        self.assertEqual(respuesta.status_code, 200)
        self.assertGreater(respuesta.content.count(b"/Type /Page\n"), 1)

        hoja = leer_excel(
            self.client.get(
                reverse("sgr_maestros:exportar_catalogo_excel"), {"q": "MAS-"}
            )
        )
        self.assertEqual(len(filas_de_datos(hoja)), 120)


class PruebasPieDePagina(SimpleTestCase):

    def test_cp_exp_015_pie_muestra_pagina_x_de_y(self):
        salida = BytesIO()
        lienzo = exportar.NumberedCanvas(
            salida, pagesize=letter, pageCompression=0
        )
        for _ in range(3):
            lienzo.drawString(100, 700, "contenido")
            lienzo.showPage()
        lienzo.save()

        pdf = salida.getvalue()
        for numero in (1, 2, 3):
            self.assertIn(f" {numero} de 3)".encode(), pdf)
        self.assertNotIn(b" de 4)", pdf)


# ============================================================
# BOTONES EN LOS LISTADOS
# ============================================================

class PruebasBotonesExportacion(BaseExportacion):

    def test_cp_exp_016_botones_conservan_los_filtros(self):
        self.client.force_login(self.admin)
        listados = [
            ("sgr_maestros:catalogo_lista", "sgr_maestros:exportar_catalogo_excel",
             "sgr_maestros:exportar_catalogo_pdf"),
            ("sgr_maestros:periodo_lista", "sgr_maestros:exportar_periodos_excel",
             "sgr_maestros:exportar_periodos_pdf"),
            ("sgr_maestros:meta_lista", "sgr_maestros:exportar_metas_excel",
             "sgr_maestros:exportar_metas_pdf"),
            ("compromiso_lista", "exportar_compromisos_excel",
             "exportar_compromisos_pdf"),
            ("delegacion_lista", "exportar_delegaciones_excel",
             "exportar_delegaciones_pdf"),
        ]
        for lista, excel, pdf in listados:
            with self.subTest(lista=lista):
                respuesta = self.client.get(reverse(lista), {"q": "abc"})
                self.assertContains(respuesta, f'href="{reverse(excel)}?q=abc"')
                self.assertContains(respuesta, f'href="{reverse(pdf)}?q=abc"')
                self.assertContains(respuesta, "Exportar a Excel")
                self.assertContains(respuesta, "Exportar a PDF")

        self.client.force_login(self.administrativo_centro)
        respuesta = self.client.get(reverse("actividades:lista"))
        self.assertContains(respuesta, reverse("actividades:exportar_excel"))
        self.assertContains(respuesta, reverse("actividades:exportar_pdf"))
