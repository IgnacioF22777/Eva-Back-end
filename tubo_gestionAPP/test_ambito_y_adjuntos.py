import shutil
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from delegacionesAPP.models import Delegacion, Servicio
from seguridadAPP.perfiles import ADMINISTRADOR, ADMINISTRATIVO, SUPERVISOR
from seguridadAPP.roles import sincronizar_roles
from sgr_maestrosAPP.forms import (
    CatalogoActividadForm,
    DetallePeriodoForm,
    MetaForm,
)
from sgr_maestrosAPP.models import CatalogoActividad, Periodo

from . import adjuntos as reglas_adjuntos
from .forms import RegistroAvanceForm
from .models import (
    AdjuntoAvance,
    AsignacionCompromiso,
    Compromiso,
    RegistroAvance,
)
from .tests import crear_usuario


MEDIA_TEMPORAL = tempfile.mkdtemp(prefix="sgr_media_test_")


def crear_delegacion(nombre):
    return Delegacion.objects.create(
        nombre=nombre,
        direccion="Dirección de prueba",
        encargado="Encargado",
        email=f"{nombre.lower().replace(' ', '')}@laserena.cl",
        telefono="51 2 000 000",
        celular="",
    )


def archivo(nombre, contenido=b"contenido de prueba", tipo="application/pdf"):
    return SimpleUploadedFile(nombre, contenido, content_type=tipo)


class BaseAmbito(TestCase):
    """Dos delegaciones con un compromiso asignado en cada una."""

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
        cls.supervisor_centro = crear_usuario(
            "12.345.678-5", "sup.centro@laserena.cl", SUPERVISOR,
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
        cls.administrativo_sin_delegacion = crear_usuario(
            "13.333.333-3", "adm.sin@laserena.cl", ADMINISTRATIVO
        )

    def setUp(self):
        self.compromiso_centro = self.crear_asignado(
            "Luminarias del centro", self.centro, self.servicio_centro
        )
        self.compromiso_rural = self.crear_asignado(
            "Riego de plazas rurales", self.rural, self.servicio_rural
        )
        self.compromiso_libre = Compromiso.objects.create(
            tarea="Compromiso sin asignar"
        )

    def crear_asignado(self, tarea, delegacion, servicio):
        compromiso = Compromiso.objects.create(
            tarea=tarea,
            cumplimiento=10,
            delegacion=delegacion,
            servicio=servicio,
        )
        AsignacionCompromiso.objects.create(
            compromiso=compromiso,
            delegacion=delegacion,
            servicio=servicio,
            usuario_asignador=self.admin,
        )
        return compromiso

    def url(self, nombre, compromiso):
        return reverse(nombre, args=[compromiso.pk])


# ============================================================
# 1. ÁMBITO TERRITORIAL POR DELEGACIÓN
# ============================================================

class PruebasAmbitoDelegacion(BaseAmbito):

    # --- TABLERO ---
    def test_administrativo_solo_ve_su_delegacion(self):
        self.client.force_login(self.administrativo_centro)
        respuesta = self.client.get(reverse("compromiso_lista"))

        self.assertContains(respuesta, "Luminarias del centro")
        self.assertNotContains(respuesta, "Riego de plazas rurales")
        self.assertNotContains(respuesta, "Compromiso sin asignar")

    def test_supervisor_ve_su_delegacion_y_los_sin_asignar(self):
        self.client.force_login(self.supervisor_centro)
        respuesta = self.client.get(reverse("compromiso_lista"))

        self.assertContains(respuesta, "Luminarias del centro")
        self.assertContains(respuesta, "Compromiso sin asignar")
        self.assertNotContains(respuesta, "Riego de plazas rurales")

    def test_administrador_ve_todas_las_delegaciones(self):
        self.client.force_login(self.admin)
        respuesta = self.client.get(reverse("compromiso_lista"))

        self.assertContains(respuesta, "Luminarias del centro")
        self.assertContains(respuesta, "Riego de plazas rurales")
        self.assertContains(respuesta, "Compromiso sin asignar")

    def test_resumen_del_tablero_cuenta_solo_lo_visible(self):
        self.client.force_login(self.administrativo_centro)
        respuesta = self.client.get(reverse("compromiso_lista"))

        self.assertEqual(respuesta.context["total_activos"], 1)
        self.assertEqual(respuesta.context["resumen"]["rojo"], 1)

    def test_busqueda_no_salta_el_ambito(self):
        self.client.force_login(self.administrativo_centro)
        respuesta = self.client.get(
            reverse("compromiso_lista"), {"q": "Rural"}
        )

        self.assertNotContains(respuesta, "Riego de plazas rurales")

    # --- T2: AVANCE ---
    def test_administrativo_no_registra_avance_en_otra_delegacion(self):
        self.client.force_login(self.administrativo_centro)

        respuesta = self.client.post(
            self.url("compromiso_avance", self.compromiso_rural),
            {"porcentaje_avance": 95, "evidencia": "Acta ajena"},
        )

        self.assertEqual(respuesta.status_code, 403)
        self.assertEqual(RegistroAvance.objects.count(), 0)

        self.compromiso_rural.refresh_from_db()
        self.assertEqual(self.compromiso_rural.cumplimiento, 10)

    def test_administrativo_tampoco_abre_el_formulario_ajeno(self):
        self.client.force_login(self.administrativo_centro)

        respuesta = self.client.get(
            self.url("compromiso_avance", self.compromiso_rural)
        )
        self.assertEqual(respuesta.status_code, 403)
        self.assertContains(
            respuesta, "pertenece a otra delegación", status_code=403
        )

    def test_administrativo_registra_avance_en_su_delegacion(self):
        self.client.force_login(self.administrativo_rural)

        respuesta = self.client.post(
            self.url("compromiso_avance", self.compromiso_rural),
            {"porcentaje_avance": 95, "evidencia": "Acta de riego"},
        )

        self.assertRedirects(
            respuesta, self.url("compromiso_historial", self.compromiso_rural)
        )
        self.compromiso_rural.refresh_from_db()
        self.assertEqual(self.compromiso_rural.cumplimiento, 95)

    def test_avance_se_revalida_si_el_compromiso_cambia_de_delegacion(self):
        """
        Simula la carrera: el formulario se abrió cuando el compromiso era
        de la delegación del usuario, pero antes del POST se reasignó.
        """
        self.client.force_login(self.administrativo_centro)
        self.assertEqual(
            self.client.get(
                self.url("compromiso_avance", self.compromiso_centro)
            ).status_code,
            200,
        )

        Compromiso.objects.filter(pk=self.compromiso_centro.pk).update(
            delegacion=self.rural, servicio=self.servicio_rural
        )

        respuesta = self.client.post(
            self.url("compromiso_avance", self.compromiso_centro),
            {"porcentaje_avance": 50, "evidencia": "Acta"},
        )

        self.assertEqual(respuesta.status_code, 403)
        self.assertEqual(RegistroAvance.objects.count(), 0)

    def test_historial_de_otra_delegacion_es_403(self):
        self.client.force_login(self.administrativo_centro)

        respuesta = self.client.get(
            self.url("compromiso_historial", self.compromiso_rural)
        )
        self.assertEqual(respuesta.status_code, 403)

    # --- T1: ASIGNACIÓN ---
    def test_supervisor_asigna_compromiso_libre_a_su_delegacion(self):
        self.client.force_login(self.supervisor_centro)

        respuesta = self.client.post(
            self.url("compromiso_asignar", self.compromiso_libre),
            {
                "delegacion": self.centro.pk,
                "servicio": self.servicio_centro.pk,
            },
        )

        self.assertRedirects(
            respuesta, self.url("compromiso_historial", self.compromiso_libre)
        )
        self.compromiso_libre.refresh_from_db()
        self.assertEqual(self.compromiso_libre.delegacion, self.centro)

    def test_supervisor_no_asigna_a_otra_delegacion(self):
        self.client.force_login(self.supervisor_centro)

        respuesta = self.client.post(
            self.url("compromiso_asignar", self.compromiso_libre),
            {
                "delegacion": self.rural.pk,
                "servicio": self.servicio_rural.pk,
            },
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertTrue(respuesta.context["form"].errors)
        self.assertFalse(
            AsignacionCompromiso.objects.filter(
                compromiso=self.compromiso_libre
            ).exists()
        )

    def test_formulario_de_asignacion_solo_ofrece_su_delegacion(self):
        self.client.force_login(self.supervisor_centro)

        respuesta = self.client.get(
            self.url("compromiso_asignar", self.compromiso_libre)
        )
        form = respuesta.context["form"]

        self.assertEqual(
            list(form.fields["delegacion"].queryset), [self.centro]
        )
        self.assertEqual(
            list(form.fields["servicio"].queryset), [self.servicio_centro]
        )

    def test_supervisor_no_opera_compromisos_de_otra_delegacion(self):
        self.client.force_login(self.supervisor_centro)

        for nombre in ("compromiso_asignar", "compromiso_editar"):
            respuesta = self.client.get(
                self.url(nombre, self.compromiso_rural)
            )
            self.assertEqual(respuesta.status_code, 403, nombre)

        respuesta = self.client.post(
            self.url("compromiso_cambiar_estado", self.compromiso_rural)
        )
        self.assertEqual(respuesta.status_code, 403)

        self.compromiso_rural.refresh_from_db()
        self.assertTrue(self.compromiso_rural.activo)

    def test_administrador_reasigna_entre_delegaciones(self):
        self.client.force_login(self.admin)

        respuesta = self.client.post(
            self.url("compromiso_asignar", self.compromiso_centro),
            {
                "delegacion": self.rural.pk,
                "servicio": self.servicio_rural.pk,
            },
        )

        self.assertRedirects(
            respuesta, self.url("compromiso_historial", self.compromiso_centro)
        )
        self.compromiso_centro.refresh_from_db()
        self.assertEqual(self.compromiso_centro.delegacion, self.rural)

    # --- SIN DELEGACIÓN: SE DENIEGA POR DEFECTO ---
    def test_usuario_sin_delegacion_no_ve_ni_opera_compromisos(self):
        self.client.force_login(self.administrativo_sin_delegacion)

        respuesta = self.client.get(reverse("compromiso_lista"))
        self.assertEqual(respuesta.status_code, 200)
        self.assertNotContains(respuesta, "Luminarias del centro")
        self.assertContains(respuesta, "no tiene una delegación asignada")

        respuesta = self.client.post(
            self.url("compromiso_avance", self.compromiso_centro),
            {"porcentaje_avance": 50, "evidencia": "Acta"},
        )
        self.assertEqual(respuesta.status_code, 403)
        self.assertEqual(RegistroAvance.objects.count(), 0)

    # --- PANELES ---
    def test_panel_administrativo_resume_solo_su_delegacion(self):
        self.client.force_login(self.administrativo_centro)
        respuesta = self.client.get(
            reverse("seguridad:panel_administrativo")
        )

        # Solo su compromiso: ni el de Rural ni el pendiente de asignar.
        self.assertEqual(respuesta.context["compromisos"]["total"], 1)
        self.assertEqual(
            list(respuesta.context["ultimos_compromisos"]),
            [self.compromiso_centro],
        )

    def test_panel_supervisor_resume_su_delegacion(self):
        self.client.force_login(self.supervisor_centro)
        respuesta = self.client.get(reverse("seguridad:panel_supervisor"))

        # Su compromiso y el que está pendiente de asignar.
        self.assertEqual(respuesta.context["compromisos"]["total"], 2)


class PruebasDelegacionObligatoria(BaseAmbito):
    """El formulario de usuarios exige delegación a quien opera por ámbito."""

    def datos(self, rol, **cambios):
        datos = {
            "rut": "9.876.543-3",
            "first_name": "Ana",
            "last_name": "Rojas",
            "email": "ana.rojas@laserena.cl",
            "groups": [Group.objects.get(name=rol).pk],
            "password1": "ClaveSegura#2026",
            "password2": "ClaveSegura#2026",
            "is_active": "on",
        }
        datos.update(cambios)
        return datos

    def test_supervisor_y_administrativo_exigen_delegacion(self):
        self.client.force_login(self.admin)

        for rol in (SUPERVISOR, ADMINISTRATIVO):
            respuesta = self.client.post(
                reverse("seguridad:usuario_crear"), self.datos(rol)
            )
            self.assertEqual(respuesta.status_code, 200, rol)
            self.assertContains(respuesta, "debe tener una delegación")

        self.assertFalse(
            Group.objects.get(name=SUPERVISOR).user_set.filter(
                email="ana.rojas@laserena.cl"
            ).exists()
        )

    def test_administrador_no_necesita_delegacion(self):
        self.client.force_login(self.admin)

        respuesta = self.client.post(
            reverse("seguridad:usuario_crear"), self.datos(ADMINISTRADOR)
        )
        self.assertRedirects(respuesta, reverse("seguridad:usuario_lista"))

    def test_no_ofrece_delegaciones_dadas_de_baja(self):
        self.rural.activo = False
        self.rural.save()
        self.client.force_login(self.admin)

        respuesta = self.client.get(reverse("seguridad:usuario_crear"))
        delegaciones = respuesta.context["form"].fields["delegacion"].queryset

        self.assertIn(self.centro, delegaciones)
        self.assertNotIn(self.rural, delegaciones)


# ============================================================
# 2. LÍMITES DE LARGO EN LOS TEXTOS
# ============================================================

class PruebasLargoDeTextos(BaseAmbito):

    def test_catalogo_rechaza_descripcion_demasiado_larga(self):
        datos = {"codigo": "ACT-1", "nombre": "Actividad", "activo": True}

        self.assertTrue(
            CatalogoActividadForm({**datos, "descripcion": "a" * 1000}).is_valid()
        )
        form = CatalogoActividadForm({**datos, "descripcion": "a" * 1001})
        self.assertFalse(form.is_valid())
        self.assertIn("descripcion", form.errors)

    def test_meta_y_detalle_rechazan_textos_demasiado_largos(self):
        periodo = Periodo.objects.create(
            codigo="PER-1", nombre="Periodo",
            fecha_inicio="2026-01-01", fecha_fin="2026-12-31",
        )
        actividad = CatalogoActividad.objects.create(
            codigo="ACT-1", nombre="Actividad"
        )

        meta = MetaForm({
            "codigo": "META-1", "nombre": "Meta", "descripcion": "x" * 1001,
            "periodo": periodo.pk, "actividad": actividad.pk,
            "valor_objetivo": "10", "ponderacion": "20", "activo": True,
        })
        self.assertIn("descripcion", meta.errors)

        detalle = DetallePeriodoForm({
            "periodo": periodo.pk, "nombre": "Primer semestre",
            "fecha_inicio": "2026-01-01", "fecha_fin": "2026-06-30",
            "observaciones": "x" * 1001,
        })
        self.assertIn("observaciones", detalle.errors)

    def test_avance_rechaza_evidencia_demasiado_larga(self):
        self.client.force_login(self.administrativo_centro)

        respuesta = self.client.post(
            self.url("compromiso_avance", self.compromiso_centro),
            {"porcentaje_avance": 50, "evidencia": "E" * 2001},
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(RegistroAvance.objects.count(), 0)

    def test_el_html_informa_el_maximo(self):
        form = RegistroAvanceForm()

        self.assertIn('maxlength="2000"', str(form["evidencia"]))
        self.assertIn('maxlength="1000"', str(form["observacion"]))

    def test_el_modelo_tambien_valida_el_largo(self):
        registro = RegistroAvance(
            compromiso=self.compromiso_centro,
            usuario_registro=self.administrativo_centro,
            porcentaje_avance=50,
            evidencia="Acta",
            observacion="o" * 1001,
        )

        with self.assertRaises(ValidationError):
            registro.full_clean()


# ============================================================
# 3. ARCHIVOS ADJUNTOS EN LOS AVANCES
# ============================================================

@override_settings(MEDIA_ROOT=MEDIA_TEMPORAL)
class PruebasAdjuntos(BaseAmbito):

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA_TEMPORAL, ignore_errors=True)

    def setUp(self):
        super().setUp()
        shutil.rmtree(MEDIA_TEMPORAL, ignore_errors=True)
        Path(MEDIA_TEMPORAL).mkdir(parents=True, exist_ok=True)

    def archivos_en_disco(self):
        return [p for p in Path(MEDIA_TEMPORAL).rglob("*") if p.is_file()]

    def registrar(self, adjuntos, usuario=None, compromiso=None, **datos):
        self.client.force_login(usuario or self.administrativo_centro)
        cuerpo = {
            "porcentaje_avance": 60,
            "evidencia": "Acta de terreno",
            "adjuntos": adjuntos,
        }
        cuerpo.update(datos)

        return self.client.post(
            self.url("compromiso_avance", compromiso or self.compromiso_centro),
            cuerpo,
        )

    # --- SUBIDA ---
    def test_avance_con_varios_archivos_de_distinto_tipo(self):
        respuesta = self.registrar([
            archivo("acta firmada.pdf"),
            archivo("foto_terreno.jpg", b"\xff\xd8\xff", "image/jpeg"),
            archivo("planilla.xlsx", b"PK\x03\x04"),
        ])

        self.assertRedirects(
            respuesta, self.url("compromiso_historial", self.compromiso_centro)
        )

        registro = RegistroAvance.objects.get()
        nombres = sorted(a.nombre_original for a in registro.adjuntos.all())
        self.assertEqual(
            nombres, ["acta firmada.pdf", "foto_terreno.jpg", "planilla.xlsx"]
        )
        self.assertEqual(len(self.archivos_en_disco()), 3)

        # En el disco el nombre es aleatorio: el original no forma parte
        # de la ruta del servidor.
        for adjunto in registro.adjuntos.all():
            self.assertNotIn("acta", adjunto.archivo.name)
            self.assertTrue(adjunto.archivo.name.startswith("avances/"))

    def test_avance_sin_archivos_sigue_siendo_valido(self):
        respuesta = self.registrar([])

        self.assertEqual(respuesta.status_code, 302)
        self.assertEqual(AdjuntoAvance.objects.count(), 0)

    # --- LÍMITES ---
    def test_rechaza_ejecutables_y_scripts(self):
        for nombre in ("virus.exe", "script.sh", "pagina.html", "foto.jpg.exe"):
            respuesta = self.registrar([archivo(nombre)])

            self.assertEqual(respuesta.status_code, 200, nombre)
            self.assertContains(respuesta, "no está permitido")

        self.assertEqual(RegistroAvance.objects.count(), 0)
        self.assertEqual(self.archivos_en_disco(), [])

    def test_rechaza_mas_archivos_que_el_maximo(self):
        archivos = [
            archivo(f"doc{i}.pdf")
            for i in range(reglas_adjuntos.MAX_ARCHIVOS + 1)
        ]
        respuesta = self.registrar(archivos)

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "como máximo")
        self.assertEqual(RegistroAvance.objects.count(), 0)

    def test_rechaza_archivo_que_supera_el_tamano_por_archivo(self):
        with patch.object(reglas_adjuntos, "MAX_BYTES_POR_ARCHIVO", 10):
            respuesta = self.registrar([archivo("grande.pdf", b"x" * 11)])

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "máximo por archivo")
        self.assertEqual(RegistroAvance.objects.count(), 0)

    def test_rechaza_cuando_el_total_supera_el_maximo(self):
        with patch.object(reglas_adjuntos, "MAX_BYTES_TOTAL", 15):
            respuesta = self.registrar([
                archivo("a.pdf", b"x" * 10),
                archivo("b.pdf", b"x" * 10),
            ])

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "máximo por avance")
        self.assertEqual(RegistroAvance.objects.count(), 0)

    def test_rechaza_archivo_vacio(self):
        respuesta = self.registrar([archivo("vacio.pdf", b"")])

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(RegistroAvance.objects.count(), 0)

    def test_rechaza_nombre_de_archivo_demasiado_largo(self):
        nombre = "a" * 200 + ".pdf"
        respuesta = self.registrar([archivo(nombre)])

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(RegistroAvance.objects.count(), 0)

    # --- ATOMICIDAD ---
    def test_si_la_transaccion_falla_no_quedan_archivos_huerfanos(self):
        with patch(
            "tubo_gestionAPP.views.Compromiso.save",
            side_effect=RuntimeError("fallo simulado"),
        ):
            with self.assertRaises(RuntimeError):
                self.registrar([archivo("acta.pdf"), archivo("foto.jpg")])

        self.assertEqual(RegistroAvance.objects.count(), 0)
        self.assertEqual(AdjuntoAvance.objects.count(), 0)
        self.assertEqual(self.archivos_en_disco(), [])

    def test_avance_rechazado_por_regla_no_deja_archivos(self):
        # El avance no puede retroceder: 5% < 10% actual.
        respuesta = self.registrar(
            [archivo("acta.pdf")], porcentaje_avance=5
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "no puede ser menor")
        self.assertEqual(self.archivos_en_disco(), [])

    # --- DESCARGA PROTEGIDA ---
    def subir_uno(self):
        self.registrar([archivo("acta firmada.pdf", b"%PDF-1.4 prueba")])
        return AdjuntoAvance.objects.get()

    def test_descarga_entrega_el_archivo_con_su_nombre_original(self):
        adjunto = self.subir_uno()
        url = reverse("adjunto_descargar", args=[adjunto.pk])

        respuesta = self.client.get(url)

        self.assertEqual(respuesta.status_code, 200)
        self.assertIn("attachment", respuesta["Content-Disposition"])
        self.assertIn("acta firmada.pdf", respuesta["Content-Disposition"])
        self.assertEqual(
            b"".join(respuesta.streaming_content), b"%PDF-1.4 prueba"
        )

    def test_descarga_respeta_el_ambito(self):
        adjunto = self.subir_uno()
        url = reverse("adjunto_descargar", args=[adjunto.pk])

        self.client.force_login(self.administrativo_rural)
        self.assertEqual(self.client.get(url).status_code, 403)

        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(url).status_code, 200)

    def test_descarga_requiere_sesion(self):
        adjunto = self.subir_uno()
        self.client.logout()

        respuesta = self.client.get(
            reverse("adjunto_descargar", args=[adjunto.pk])
        )
        self.assertEqual(respuesta.status_code, 302)
        self.assertIn(reverse("seguridad:login"), respuesta["Location"])

    def test_historial_muestra_el_enlace_de_descarga(self):
        adjunto = self.subir_uno()

        respuesta = self.client.get(
            self.url("compromiso_historial", self.compromiso_centro)
        )

        self.assertContains(respuesta, "acta firmada.pdf")
        self.assertContains(
            respuesta, reverse("adjunto_descargar", args=[adjunto.pk])
        )

    def test_formulario_de_avance_acepta_archivos(self):
        self.client.force_login(self.administrativo_centro)
        respuesta = self.client.get(
            self.url("compromiso_avance", self.compromiso_centro)
        )

        self.assertContains(respuesta, 'enctype="multipart/form-data"')
        self.assertContains(respuesta, 'type="file"')
        self.assertContains(respuesta, "multiple")
