"""
Evaluación 3 - Organizaciones comunitarias e importación del registro de
juntas de vecinos (2.709 organizaciones).

Cada prueba tiene un ID CP-ORG-xxx para la matriz de resultado esperado
vs. obtenido del informe. Se incluyen casos normales y de borde.
"""
import tempfile
import zipfile
from datetime import date, timedelta
from io import StringIO
from pathlib import Path
from xml.sax.saxutils import escape

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.urls import reverse

from delegacionesAPP.models import Delegacion
from seguridadAPP.perfiles import ADMINISTRADOR, ADMINISTRATIVO, SUPERVISOR
from seguridadAPP.roles import sincronizar_roles
from tubo_gestionAPP.tests import crear_usuario

from .models import OrganizacionComunitaria, tipo_por_nombre


ENCABEZADOS = [
    "ORGANIZACIONES", "DOMICILIO LEGAL ", "TERRIT. DELEG.", "SOCIOS ACTIVOS",
    "FECHA CONSTIT.", "Nº REG. P.J.", "FECHA INSCRIPC EN REG.", "REG. DIR. Nº",
]


def serial(fecha):
    """Fecha -> número serial de Excel (como viene en la planilla)."""
    return str((fecha - date(1899, 12, 30)).days)


def crear_xlsx(filas, encabezados=ENCABEZADOS):
    """Crea una planilla .xlsx mínima (celdas de texto en línea y números)."""
    def celda(col, fila, valor):
        ref = f"{chr(65 + col)}{fila}"
        if isinstance(valor, (int, float)):
            return f'<c r="{ref}"><v>{valor}</v></c>'
        return f'<c r="{ref}" t="inlineStr"><is><t>{escape(str(valor))}</t></is></c>'

    filas_xml = []
    for i, fila in enumerate([encabezados] + filas, start=1):
        celdas = "".join(celda(c, i, v) for c, v in enumerate(fila) if v != "")
        filas_xml.append(f'<row r="{i}">{celdas}</row>')

    ns = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
    rel = 'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"'
    carpeta = tempfile.mkdtemp(prefix="sgr_jjvv_")
    ruta = Path(carpeta) / "registro.xlsx"
    with zipfile.ZipFile(ruta, "w") as z:
        z.writestr("xl/workbook.xml",
                   f'<workbook {ns} {rel}><sheets><sheet name="juntas de vecinos" sheetId="1" r:id="rId1"/></sheets></workbook>')
        z.writestr("xl/_rels/workbook.xml.rels",
                   '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   '<Relationship Id="rId1" Type="worksheet" Target="worksheets/sheet1.xml"/></Relationships>')
        z.writestr("xl/worksheets/sheet1.xml",
                   f'<worksheet {ns}><sheetData>{"".join(filas_xml)}</sheetData></worksheet>')
    return str(ruta)


def importar(ruta, *opciones):
    salida = StringIO()
    call_command("importar_organizaciones", ruta, *opciones, stdout=salida)
    return salida.getvalue()


CONSTITUCION = date(2020, 3, 10)
INSCRIPCION = date(2020, 4, 2)


def fila(nombre, territorio="CENTRO", registro="100", socios="25",
         constitucion=None, inscripcion=None, domicilio="Calle 1", directiva="900"):
    return [
        nombre, domicilio, territorio, socios,
        serial(constitucion or CONSTITUCION) if constitucion != "" else "",
        registro,
        serial(inscripcion or INSCRIPCION) if inscripcion != "" else "",
        directiva,
    ]


class BaseOrganizaciones(TestCase):

    @classmethod
    def setUpTestData(cls):
        sincronizar_roles()
        nombres = ["Delegación Centro", "Delegación Av. del Mar", "Delegación La Pampa",
                   "Delegación Las Compañías", "Delegación Rural", "Delegación La Antena - La Florida"]
        cls.delegaciones = {}
        for nombre in nombres:
            cls.delegaciones[nombre] = Delegacion.objects.create(
                nombre=nombre, direccion="Dir", encargado="Enc",
                email=f"{len(cls.delegaciones)}@laserena.cl", telefono="1", celular="1",
            )
        cls.centro = cls.delegaciones["Delegación Centro"]
        cls.pampa = cls.delegaciones["Delegación La Pampa"]


# ============================================================
# IMPORTACIÓN
# ============================================================

class PruebasImportacion(BaseOrganizaciones):

    def test_CP_ORG_001_importa_y_asigna_delegacion_y_tipo(self):
        """CP-ORG-001: importa las filas, asocia el territorio a su delegación y sugiere el tipo por el nombre."""
        ruta = crear_xlsx([
            fila("JUNTA DE VECINOS VILLA EL INDIO", "CIAS", "1"),
            fila("CLUB DEPORTIVO LOS LEONES", "AV DEL MAR", "2"),
            fila("CLUB DE ADULTO MAYOR ALEGRIA", "PAMPA", "3"),
            fila("CENTRO CULTURAL RAICES", "ANTENA", "4"),
            fila("COMITE DE SEGURIDAD LAS ROSAS", "RURAL", "5"),
            fila("AGRUPACION AMIGOS", "CENTRO", "6"),
        ])
        salida = importar(ruta)

        self.assertIn("6 creadas", salida)
        org = OrganizacionComunitaria.objects.get(numero_registro="1")
        self.assertEqual(org.delegacion.nombre, "Delegación Las Compañías")
        self.assertEqual(org.tipo, OrganizacionComunitaria.JUNTA_VECINOS)
        self.assertEqual(org.fecha_constitucion, CONSTITUCION)
        self.assertEqual(org.fecha_inscripcion, INSCRIPCION)
        self.assertFalse(org.verificada)
        self.assertEqual(
            OrganizacionComunitaria.objects.get(numero_registro="2").delegacion.nombre,
            "Delegación Av. del Mar",
        )
        tipos = dict(OrganizacionComunitaria.objects.values_list("numero_registro", "tipo"))
        self.assertEqual(tipos, {
            "1": "JUNTA_VECINOS", "2": "DEPORTIVA", "3": "ADULTO_MAYOR",
            "4": "CULTURAL", "5": "COMITE", "6": "FUNCIONAL",
        })

    def test_CP_ORG_002_reimportar_no_duplica(self):
        """CP-ORG-002: importar dos veces deja las mismas organizaciones e informa «sin cambios»."""
        ruta = crear_xlsx([fila("JUNTA A", registro="1"), fila("JUNTA B", registro="2")])
        importar(ruta)
        salida = importar(ruta)

        self.assertEqual(OrganizacionComunitaria.objects.count(), 2)
        self.assertIn("0 creadas, 0 actualizadas, 2 sin cambios", salida)

    def test_CP_ORG_003_simulacion_no_guarda(self):
        """CP-ORG-003: --dry-run informa el resultado sin guardar."""
        salida = importar(crear_xlsx([fila("JUNTA A")]), "--dry-run")

        self.assertIn("SIMULACIÓN", salida)
        self.assertIn("1 creadas", salida)
        self.assertFalse(OrganizacionComunitaria.objects.exists())

    def test_CP_ORG_004_fechas_sin_informacion(self):
        """CP-ORG-004 (borde): «S/Inf.» y el serial 0/1 de Excel quedan sin fecha y con advertencia."""
        ruta = crear_xlsx([
            ["SIN INFO", "", "CENTRO", "10", "S/Inf.", "1", serial(INSCRIPCION), ""],
            ["SERIAL VACIO", "", "CENTRO", "10", "1", "2", serial(INSCRIPCION), ""],
        ])
        salida = importar(ruta)

        sin_info = OrganizacionComunitaria.objects.get(numero_registro="1")
        self.assertIsNone(sin_info.fecha_constitucion)
        self.assertIn("S/Inf.", sin_info.observaciones)
        self.assertIsNone(OrganizacionComunitaria.objects.get(numero_registro="2").fecha_constitucion)
        self.assertIn("fecha de constitución sin información", salida)

    def test_CP_ORG_005_socios_con_texto(self):
        """CP-ORG-005 (borde): «6 CLUBES» y «32!» se leen como 6 y 32; un espacio queda vacío."""
        ruta = crear_xlsx([
            fila("UNION COMUNAL", registro="1", socios="6 CLUBES"),
            fila("CLUB X", registro="2", socios="32!"),
            fila("CLUB Y", registro="3", socios=" "),
        ])
        importar(ruta)

        socios = dict(OrganizacionComunitaria.objects.values_list("numero_registro", "socios_activos"))
        self.assertEqual(socios, {"1": 6, "2": 32, "3": None})
        self.assertIn("6 CLUBES", OrganizacionComunitaria.objects.get(numero_registro="1").observaciones)

    def test_CP_ORG_006_registro_repetido_para_organizaciones_distintas(self):
        """CP-ORG-006 (borde): el mismo N° de registro con nombres distintos carga ambas y lo advierte."""
        ruta = crear_xlsx([
            fila("CENTRO DE PADRES PRINCIPITO", "CIAS", "4008"),
            fila("MOVIMIENTO BIENESTAR Y ALEGRIA", "CIAS", "4008"),
        ])
        salida = importar(ruta)

        self.assertEqual(OrganizacionComunitaria.objects.filter(numero_registro="4008").count(), 2)
        self.assertIn("número de registro repetido", salida)

    def test_CP_ORG_007_territorio_vacio_o_desconocido(self):
        """CP-ORG-007 (borde): sin territorio o con «ALFALFARES» queda sin delegación y con aviso."""
        ruta = crear_xlsx([
            fila("ORG SIN TERRITORIO", "", "1"),
            fila("ORG ALFALFARES", "ALFALFARES", "2"),
        ])
        salida = importar(ruta)

        self.assertFalse(OrganizacionComunitaria.objects.filter(delegacion__isnull=False).exists())
        self.assertEqual(
            OrganizacionComunitaria.objects.get(numero_registro="2").territorio_origen, "ALFALFARES"
        )
        self.assertIn("territorio vacío", salida)
        self.assertIn("ALFALFARES sin delegación", salida)

    def test_CP_ORG_008_no_modifica_organizaciones_verificadas(self):
        """CP-ORG-008 (borde): una organización verificada no se modifica al reimportar."""
        importar(crear_xlsx([fila("JUNTA A", socios="25")]))
        org = OrganizacionComunitaria.objects.get()
        org.verificada = True
        org.socios_activos = 40
        org.save()

        salida = importar(crear_xlsx([fila("JUNTA A", socios="99")]))

        org.refresh_from_db()
        self.assertEqual(org.socios_activos, 40)
        self.assertIn("1 verificadas (no se modifican)", salida)

    def test_CP_ORG_009_actualiza_datos_no_verificados(self):
        """CP-ORG-009: si la planilla trae datos nuevos de una organización no verificada, se actualiza."""
        importar(crear_xlsx([fila("JUNTA A", socios="25")]))
        salida = importar(crear_xlsx([fila("JUNTA A", socios="30", territorio="PAMPA")]))

        org = OrganizacionComunitaria.objects.get()
        self.assertEqual(org.socios_activos, 30)
        self.assertEqual(org.delegacion, self.pampa)
        self.assertIn("1 actualizadas", salida)

    def test_CP_ORG_010_filas_incompletas_se_omiten(self):
        """CP-ORG-010 (borde): una fila sin nombre o sin N° de registro se omite y el resto se carga."""
        ruta = crear_xlsx([
            fila("", registro="1"),
            fila("ORG SIN REGISTRO", registro=""),
            fila("ORG VALIDA", registro="3"),
        ])
        salida = importar(ruta)

        self.assertEqual(OrganizacionComunitaria.objects.count(), 1)
        self.assertIn("2 omitidas", salida)

    def test_CP_ORG_011_inscripcion_anterior_y_fecha_futura(self):
        """CP-ORG-011 (borde): inscripción anterior a la constitución y fechas futuras se cargan con aviso."""
        ruta = crear_xlsx([
            fila("ORG FECHAS CRUZADAS", registro="1",
                 constitucion=date(2012, 4, 17), inscripcion=date(2006, 4, 18)),
            fila("ORG FUTURA", registro="2", inscripcion=date.today() + timedelta(days=200)),
        ])
        salida = importar(ruta)

        self.assertEqual(OrganizacionComunitaria.objects.count(), 2)
        self.assertIn("inscripción anterior a la constitución", salida)
        self.assertIn("fecha futura", salida)

    def test_CP_ORG_012_archivos_invalidos(self):
        """CP-ORG-012 (borde): archivo inexistente, que no es .xlsx o sin las columnas esperadas se rechaza."""
        with self.assertRaisesMessage(CommandError, "No se pudo abrir"):
            importar("no-existe.xlsx")

        carpeta = tempfile.mkdtemp()
        texto = Path(carpeta) / "falso.xlsx"
        texto.write_text("no soy una planilla", encoding="utf-8")
        with self.assertRaisesMessage(CommandError, "No se pudo abrir"):
            importar(str(texto))

        sin_columnas = crear_xlsx([["X", "Y"]], encabezados=["ORGANIZACIONES", "OTRA"])
        with self.assertRaisesMessage(CommandError, "Faltan columnas"):
            importar(sin_columnas)

        self.assertFalse(OrganizacionComunitaria.objects.exists())

    def test_CP_ORG_013_clasificacion_por_palabras(self):
        """CP-ORG-013 (borde): «ARTE» no calza con «PARTE» ni «CAM» con «CAMPO»."""
        self.assertEqual(tipo_por_nombre("AGRUPACION DE ARTE URBANO"), OrganizacionComunitaria.CULTURAL)
        self.assertEqual(tipo_por_nombre("ORGANIZACION LA CONTRAPARTE"), OrganizacionComunitaria.FUNCIONAL)
        self.assertEqual(tipo_por_nombre("CAM LOS AROMOS"), OrganizacionComunitaria.ADULTO_MAYOR)
        self.assertEqual(tipo_por_nombre("AGRUPACION CAMPO VERDE"), OrganizacionComunitaria.FUNCIONAL)
        self.assertEqual(tipo_por_nombre("Junta de Vecinos Nº 5"), OrganizacionComunitaria.JUNTA_VECINOS)
        self.assertEqual(tipo_por_nombre("COMITÉ DE AGUA"), OrganizacionComunitaria.COMITE)


# ============================================================
# MANTENEDOR (CRUD, BÚSQUEDA, PERMISOS Y ÁMBITO)
# ============================================================

class PruebasMantenedor(BaseOrganizaciones):

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.admin = crear_usuario("11.111.111-1", "admin@laserena.cl", ADMINISTRADOR)
        cls.supervisor = crear_usuario("12.345.678-5", "sup@laserena.cl", SUPERVISOR, delegacion=cls.centro)
        cls.administrativo = crear_usuario("22.222.222-2", "adm@laserena.cl", ADMINISTRATIVO, delegacion=cls.centro)

    def setUp(self):
        self.org_centro = OrganizacionComunitaria.objects.create(
            nombre="JUNTA DE VECINOS CENTRO HISTORICO", numero_registro="10",
            tipo=OrganizacionComunitaria.JUNTA_VECINOS, delegacion=self.centro,
        )
        self.org_pampa = OrganizacionComunitaria.objects.create(
            nombre="CLUB DEPORTIVO LA PAMPA", numero_registro="20",
            tipo=OrganizacionComunitaria.DEPORTIVA, delegacion=self.pampa,
        )

    def datos(self, **cambios):
        datos = {
            "nombre": "AGRUPACION NUEVA", "tipo": "FUNCIONAL", "numero_registro": "999",
            "delegacion": self.centro.pk, "domicilio": "Calle 1", "socios_activos": "20",
            "fecha_constitucion": "2024-01-10", "fecha_inscripcion": "2024-02-01",
            "registro_directiva": "", "observaciones": "",
        }
        datos.update(cambios)
        return datos

    def test_CP_ORG_014_permisos_por_perfil(self):
        """CP-ORG-014: sin sesión redirige al login; el Administrativo consulta pero no crea ni edita."""
        respuesta = self.client.get(reverse("organizaciones:organizacion_lista"))
        self.assertEqual(respuesta.status_code, 302)

        self.client.force_login(self.administrativo)
        self.assertEqual(self.client.get(reverse("organizaciones:organizacion_lista")).status_code, 200)
        self.assertEqual(self.client.get(reverse("organizaciones:organizacion_crear")).status_code, 403)
        self.assertEqual(
            self.client.get(reverse("organizaciones:organizacion_editar", args=[self.org_centro.pk])).status_code,
            403,
        )

    def test_CP_ORG_015_busqueda_y_filtros(self):
        """CP-ORG-015: busca por nombre o registro y filtra por tipo, delegación y verificación."""
        self.client.force_login(self.admin)
        url = reverse("organizaciones:organizacion_lista")

        respuesta = self.client.get(url, {"q": "historico"})
        self.assertContains(respuesta, "CENTRO HISTORICO")
        self.assertNotContains(respuesta, "CLUB DEPORTIVO LA PAMPA")

        respuesta = self.client.get(url, {"tipo": "DEPORTIVA"})
        self.assertContains(respuesta, "CLUB DEPORTIVO LA PAMPA")
        self.assertNotContains(respuesta, "CENTRO HISTORICO")

        respuesta = self.client.get(url, {"delegacion": self.pampa.pk})
        self.assertContains(respuesta, "CLUB DEPORTIVO LA PAMPA")
        self.assertNotContains(respuesta, "CENTRO HISTORICO")

        self.org_centro.verificada = True
        self.org_centro.save()
        respuesta = self.client.get(url, {"verificacion": "no", "delegacion": ""})
        self.assertContains(respuesta, "CLUB DEPORTIVO LA PAMPA")
        self.assertNotContains(respuesta, "CENTRO HISTORICO")

    def test_CP_ORG_016_paginacion(self):
        """CP-ORG-016 (borde): con más de 50 resultados el listado se pagina."""
        OrganizacionComunitaria.objects.bulk_create([
            OrganizacionComunitaria(nombre=f"ORG {i:03d}", numero_registro=str(1000 + i), delegacion=self.centro)
            for i in range(60)
        ])
        self.client.force_login(self.admin)
        respuesta = self.client.get(reverse("organizaciones:organizacion_lista"))

        self.assertEqual(len(respuesta.context["pagina"].object_list), 50)
        self.assertContains(respuesta, "Página 1 de 2")
        respuesta = self.client.get(reverse("organizaciones:organizacion_lista"), {"pagina": 2})
        self.assertEqual(len(respuesta.context["pagina"].object_list), 12)

    def test_CP_ORG_017_supervisor_ve_solo_su_delegacion(self):
        """CP-ORG-017: el listado del Supervisor muestra solo su delegación, aunque pida «Todas»."""
        self.client.force_login(self.supervisor)
        url = reverse("organizaciones:organizacion_lista")

        respuesta = self.client.get(url)
        self.assertContains(respuesta, "CENTRO HISTORICO")
        self.assertNotContains(respuesta, "CLUB DEPORTIVO LA PAMPA")

        respuesta = self.client.get(url, {"delegacion": ""})
        self.assertContains(respuesta, "CENTRO HISTORICO")
        self.assertNotContains(respuesta, "CLUB DEPORTIVO LA PAMPA")

    def test_CP_ORG_018_supervisor_crea_en_su_delegacion(self):
        """CP-ORG-018: el Supervisor crea en su delegación; otra delegación es opción no válida."""
        self.client.force_login(self.supervisor)

        respuesta = self.client.post(reverse("organizaciones:organizacion_crear"), self.datos())
        self.assertRedirects(respuesta, reverse("organizaciones:organizacion_lista"))
        self.assertEqual(OrganizacionComunitaria.objects.get(numero_registro="999").delegacion, self.centro)

        respuesta = self.client.post(
            reverse("organizaciones:organizacion_crear"),
            self.datos(numero_registro="998", delegacion=self.pampa.pk),
        )
        self.assertEqual(respuesta.status_code, 200)
        self.assertIn("delegacion", respuesta.context["form"].errors)

    def test_CP_ORG_019_supervisor_no_modifica_otra_delegacion(self):
        """CP-ORG-019 (borde): editar, verificar o dar de baja una organización de otra delegación es 403."""
        self.client.force_login(self.supervisor)
        pk = self.org_pampa.pk

        self.assertEqual(self.client.get(reverse("organizaciones:organizacion_editar", args=[pk])).status_code, 403)
        self.assertEqual(self.client.post(reverse("organizaciones:organizacion_verificar", args=[pk])).status_code, 403)
        self.assertEqual(self.client.post(reverse("organizaciones:organizacion_cambiar_estado", args=[pk])).status_code, 403)

        self.org_pampa.refresh_from_db()
        self.assertTrue(self.org_pampa.activo)
        self.assertFalse(self.org_pampa.verificada)

    def test_CP_ORG_020_administrador_modifica_cualquiera(self):
        """CP-ORG-020: el Administrador edita organizaciones de cualquier delegación y puede dejarlas sin delegación."""
        self.client.force_login(self.admin)
        respuesta = self.client.post(
            reverse("organizaciones:organizacion_editar", args=[self.org_pampa.pk]),
            self.datos(nombre="CLUB DEPORTIVO LA PAMPA", numero_registro="20", delegacion=""),
        )
        self.assertRedirects(respuesta, reverse("organizaciones:organizacion_lista"))
        self.org_pampa.refresh_from_db()
        self.assertIsNone(self.org_pampa.delegacion)

    def test_CP_ORG_021_validaciones_del_formulario(self):
        """CP-ORG-021 (borde): fecha futura, inscripción antes de constitución y registro+nombre repetido se rechazan."""
        self.client.force_login(self.admin)
        url = reverse("organizaciones:organizacion_crear")
        futura = (date.today() + timedelta(days=5)).isoformat()

        respuesta = self.client.post(url, self.datos(fecha_constitucion=futura))
        self.assertIn("fecha_constitucion", respuesta.context["form"].errors)

        respuesta = self.client.post(url, self.datos(fecha_constitucion="2024-05-01", fecha_inscripcion="2024-01-01"))
        self.assertIn("fecha_inscripcion", respuesta.context["form"].errors)

        respuesta = self.client.post(url, self.datos(nombre="junta de vecinos  centro histórico", numero_registro="10"))
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(OrganizacionComunitaria.objects.filter(numero_registro="10").count(), 1)

    def test_CP_ORG_022_baja_logica_y_verificacion(self):
        """CP-ORG-022: dar de baja conserva el registro; verificar alterna el estado; vuelve a la página de origen."""
        self.client.force_login(self.supervisor)
        pk = self.org_centro.pk
        origen = reverse("organizaciones:organizacion_lista") + "?pagina=1"

        respuesta = self.client.post(
            reverse("organizaciones:organizacion_cambiar_estado", args=[pk]), {"volver": origen}
        )
        self.assertRedirects(respuesta, origen, fetch_redirect_response=False)
        self.org_centro.refresh_from_db()
        self.assertFalse(self.org_centro.activo)
        self.assertTrue(OrganizacionComunitaria.objects.filter(pk=pk).exists())

        self.client.post(reverse("organizaciones:organizacion_verificar", args=[pk]))
        self.org_centro.refresh_from_db()
        self.assertTrue(self.org_centro.verificada)

    def test_CP_ORG_024_listado_ignora_delegacion_de_la_url(self):
        """CP-ORG-024 (borde, seguridad): sin perfil Administrador, cambiar ?delegacion= no muestra otras delegaciones."""
        sin_delegacion = OrganizacionComunitaria.objects.create(
            nombre="COMITE SIN TERRITORIO", numero_registro="30",
            tipo=OrganizacionComunitaria.FUNCIONAL,
        )
        url = reverse("organizaciones:organizacion_lista")

        for usuario in (self.administrativo, self.supervisor):
            self.client.force_login(usuario)
            for valor in (str(self.pampa.pk), "sin", "", "abc"):
                respuesta = self.client.get(url, {"delegacion": valor})
                self.assertEqual(respuesta.status_code, 200)
                listadas = set(respuesta.context["pagina"].object_list)
                self.assertEqual(listadas, {self.org_centro}, f"{usuario} con delegacion={valor!r}")
                self.assertEqual(respuesta.context["delegacion"], str(self.centro.pk))

            # Los contadores tampoco revelan datos de otras delegaciones.
            self.assertEqual(respuesta.context["total_vigentes"], 1)
            self.assertEqual(respuesta.context["total_sin_delegacion"], 0)
            self.assertNotContains(respuesta, "Delegación La Pampa")

        # El Administrador sí puede elegir cualquier delegación o las sin asignar.
        self.client.force_login(self.admin)
        respuesta = self.client.get(url, {"delegacion": self.pampa.pk})
        self.assertEqual(set(respuesta.context["pagina"].object_list), {self.org_pampa})
        respuesta = self.client.get(url, {"delegacion": "sin"})
        self.assertEqual(set(respuesta.context["pagina"].object_list), {sin_delegacion})

    def test_CP_ORG_025_usuario_sin_delegacion_no_ve_organizaciones(self):
        """CP-ORG-025 (borde): un Administrativo sin delegación asignada no ve ninguna organización."""
        huerfano = crear_usuario("13.131.313-3", "sindel@laserena.cl", ADMINISTRATIVO)
        self.client.force_login(huerfano)

        for valor in (None, str(self.centro.pk), "sin"):
            parametros = {} if valor is None else {"delegacion": valor}
            respuesta = self.client.get(reverse("organizaciones:organizacion_lista"), parametros)
            self.assertEqual(respuesta.status_code, 200)
            self.assertEqual(respuesta.context["total_filtradas"], 0)
            self.assertEqual(respuesta.context["total_vigentes"], 0)

    def test_CP_ORG_023_no_redirige_a_sitios_externos(self):
        """CP-ORG-023 (borde, seguridad): un «volver» a otro sitio se ignora y vuelve al listado."""
        self.client.force_login(self.supervisor)
        respuesta = self.client.post(
            reverse("organizaciones:organizacion_verificar", args=[self.org_centro.pk]),
            {"volver": "https://sitio-malicioso.example/robo"},
        )
        self.assertRedirects(
            respuesta, reverse("organizaciones:organizacion_lista"), fetch_redirect_response=False
        )
