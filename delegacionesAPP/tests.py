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

from .models import Delegacion, Servicio


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


class PruebasDelegaciones(TestCase):
    """Mantenedor de Delegaciones: CRUD, búsqueda y baja lógica."""

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

    def datos(self, **cambios):
        datos = {
            "nombre": "Delegación Centro",
            "direccion": "Av. Principal 123",
            "encargado": "Ana Rojas",
            "email": "centro@laserena.cl",
            "telefono": "51 2 000 000",
            "celular": "+56 9 0000 0000",
        }
        datos.update(cambios)

        return datos

    def crear_delegacion(self, **cambios):
        datos = {
            "nombre": "Delegación Centro",
            "direccion": "Av. Principal 123",
            "encargado": "Ana Rojas",
            "email": "centro@laserena.cl",
            "telefono": "51 2 000 000",
            "celular": "+56 9 0000 0000",
        }
        datos.update(cambios)

        return Delegacion.objects.create(**datos)

    # --- ACCESO ---
    def test_lista_requiere_sesion(self):
        respuesta = self.client.get(reverse("delegacion_lista"))
        self.assertEqual(respuesta.status_code, 302)
        self.assertIn(reverse("seguridad:login"), respuesta["Location"])

    def test_administrativo_consulta_pero_no_crea(self):
        self.client.force_login(self.administrativo)

        respuesta = self.client.get(reverse("delegacion_lista"))
        self.assertEqual(respuesta.status_code, 200)

        respuesta = self.client.get(reverse("delegacion_crear"))
        self.assertEqual(respuesta.status_code, 403)

    def test_administrativo_no_puede_editar_ni_dar_de_baja(self):
        delegacion = self.crear_delegacion()
        self.client.force_login(self.administrativo)

        respuesta = self.client.get(
            reverse("delegacion_editar", args=[delegacion.pk])
        )
        self.assertEqual(respuesta.status_code, 403)

        respuesta = self.client.post(
            reverse("delegacion_cambiar_estado", args=[delegacion.pk])
        )
        self.assertEqual(respuesta.status_code, 403)

    # --- CREAR ---
    def test_supervisor_crea_delegacion(self):
        self.client.force_login(self.supervisor)

        respuesta = self.client.post(
            reverse("delegacion_crear"), self.datos()
        )

        self.assertRedirects(respuesta, reverse("delegacion_lista"))
        self.assertTrue(
            Delegacion.objects.filter(nombre="Delegación Centro").exists()
        )

    def test_crear_rechaza_nombre_delegacion_activa(self):
        self.crear_delegacion()
        self.client.force_login(self.admin)

        respuesta = self.client.post(
            reverse("delegacion_crear"), self.datos()
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(
            respuesta, "Ya existe una delegación activa con este nombre."
        )
        self.assertEqual(
            Delegacion.objects.filter(nombre="Delegación Centro").count(), 1
        )

    def test_crear_reactiva_delegacion_inactiva(self):
        inactiva = self.crear_delegacion(activo=False)
        self.client.force_login(self.admin)

        respuesta = self.client.post(
            reverse("delegacion_crear"),
            self.datos(encargado="Nuevo encargado"),
        )

        self.assertRedirects(respuesta, reverse("delegacion_lista"))

        inactiva.refresh_from_db()
        self.assertTrue(inactiva.activo)
        self.assertEqual(inactiva.encargado, "Nuevo encargado")
        self.assertEqual(
            Delegacion.objects.filter(nombre="Delegación Centro").count(), 1
        )

    # --- LISTAR Y BUSCAR ---
    def test_busqueda_por_nombre_y_encargado(self):
        self.crear_delegacion()
        self.crear_delegacion(
            nombre="Delegación Rural",
            encargado="Pedro Soto",
            email="rural@laserena.cl",
            direccion="Camino Rural km 5",
        )
        self.client.force_login(self.supervisor)

        respuesta = self.client.get(reverse("delegacion_lista"), {"q": "Rural"})
        self.assertContains(respuesta, "Delegación Rural")
        self.assertNotContains(respuesta, "Delegación Centro")

        respuesta = self.client.get(reverse("delegacion_lista"), {"q": "Ana"})
        self.assertContains(respuesta, "Delegación Centro")
        self.assertNotContains(respuesta, "Delegación Rural")

    def test_filtro_por_estado(self):
        self.crear_delegacion()
        self.crear_delegacion(
            nombre="Delegación Histórica",
            email="historica@laserena.cl",
            activo=False,
        )
        self.client.force_login(self.supervisor)

        respuesta = self.client.get(
            reverse("delegacion_lista"), {"estado": "inactivos"}
        )
        self.assertContains(respuesta, "Delegación Histórica")
        self.assertNotContains(respuesta, "Delegación Centro")

        respuesta = self.client.get(
            reverse("delegacion_lista"), {"estado": "activos"}
        )
        self.assertContains(respuesta, "Delegación Centro")
        self.assertNotContains(respuesta, "Delegación Histórica")

    # --- EDITAR ---
    def test_editar_delegacion(self):
        delegacion = self.crear_delegacion()
        self.client.force_login(self.supervisor)

        respuesta = self.client.post(
            reverse("delegacion_editar", args=[delegacion.pk]),
            self.datos(encargado="Encargado Nuevo"),
        )

        self.assertRedirects(respuesta, reverse("delegacion_lista"))

        delegacion.refresh_from_db()
        self.assertEqual(delegacion.encargado, "Encargado Nuevo")

    # --- BAJA Y REACTIVACIÓN ---
    def test_baja_logica_conserva_el_registro(self):
        delegacion = self.crear_delegacion()
        self.client.force_login(self.supervisor)

        respuesta = self.client.post(
            reverse("delegacion_cambiar_estado", args=[delegacion.pk])
        )

        self.assertRedirects(respuesta, reverse("delegacion_lista"))

        delegacion.refresh_from_db()
        self.assertFalse(delegacion.activo)
        self.assertTrue(Delegacion.objects.filter(pk=delegacion.pk).exists())

    def test_no_da_de_baja_con_servicios_activos(self):
        delegacion = self.crear_delegacion()
        Servicio.objects.create(delegacion=delegacion, nombre="Aseo")
        self.client.force_login(self.supervisor)

        respuesta = self.client.post(
            reverse("delegacion_cambiar_estado", args=[delegacion.pk]),
            follow=True,
        )

        self.assertContains(
            respuesta, "tiene servicios o compromisos activos"
        )

        delegacion.refresh_from_db()
        self.assertTrue(delegacion.activo)

    def test_no_da_de_baja_con_compromisos_activos(self):
        from tubo_gestionAPP.models import Compromiso

        delegacion = self.crear_delegacion()
        Compromiso.objects.create(
            tarea="Mejorar luminarias",
            cumplimiento=50,
            delegacion=delegacion,
        )
        self.client.force_login(self.supervisor)

        self.client.post(
            reverse("delegacion_cambiar_estado", args=[delegacion.pk])
        )

        delegacion.refresh_from_db()
        self.assertTrue(delegacion.activo)

    def test_reactiva_delegacion_dada_de_baja(self):
        delegacion = self.crear_delegacion(activo=False)
        self.client.force_login(self.supervisor)

        self.client.post(
            reverse("delegacion_cambiar_estado", args=[delegacion.pk])
        )

        delegacion.refresh_from_db()
        self.assertTrue(delegacion.activo)

    def test_no_reactiva_si_existe_otra_activa_con_el_mismo_nombre(self):
        self.crear_delegacion()
        inactiva = self.crear_delegacion(
            direccion="Otra dirección", activo=False
        )
        self.client.force_login(self.supervisor)

        self.client.post(
            reverse("delegacion_cambiar_estado", args=[inactiva.pk])
        )

        inactiva.refresh_from_db()
        self.assertFalse(inactiva.activo)

    def test_baja_exige_post(self):
        delegacion = self.crear_delegacion()
        self.client.force_login(self.supervisor)

        respuesta = self.client.get(
            reverse("delegacion_cambiar_estado", args=[delegacion.pk])
        )

        self.assertEqual(respuesta.status_code, 405)

    # --- DETALLE ---
    def test_detalle_muestra_servicios_y_permite_buscar(self):
        delegacion = self.crear_delegacion()
        Servicio.objects.create(delegacion=delegacion, nombre="Aseo")
        Servicio.objects.create(delegacion=delegacion, nombre="Iluminación")
        self.client.force_login(self.supervisor)

        respuesta = self.client.get(
            reverse("delegacion_detalle", args=[delegacion.pk])
        )
        self.assertContains(respuesta, "Aseo")
        self.assertContains(respuesta, "Iluminación")

        respuesta = self.client.get(
            reverse("delegacion_detalle", args=[delegacion.pk]),
            {"q": "Aseo"},
        )
        self.assertContains(respuesta, "Aseo")
        self.assertNotContains(respuesta, "Iluminación")


class PruebasServicios(TestCase):
    """Servicios anidados: crear, editar, buscar y baja lógica."""

    @classmethod
    def setUpTestData(cls):
        sincronizar_roles()

        cls.supervisor = crear_usuario(
            "12.345.678-5", "supervisor@laserena.cl", SUPERVISOR
        )
        cls.administrativo = crear_usuario(
            "22.222.222-2", "administrativo@laserena.cl", ADMINISTRATIVO
        )
        cls.delegacion = Delegacion.objects.create(
            nombre="Delegación Centro",
            direccion="Av. Principal 123",
            encargado="Ana Rojas",
            email="centro@laserena.cl",
            telefono="51 2 000 000",
            celular="+56 9 0000 0000",
        )

    def url_crear(self, delegacion=None):
        return reverse(
            "servicio_crear",
            args=[(delegacion or self.delegacion).pk],
        )

    def test_administrativo_no_puede_crear_servicios(self):
        self.client.force_login(self.administrativo)

        respuesta = self.client.get(self.url_crear())
        self.assertEqual(respuesta.status_code, 403)

    def test_crea_servicio(self):
        self.client.force_login(self.supervisor)

        respuesta = self.client.post(
            self.url_crear(), {"nombre": "Retiro de escombros"}
        )

        self.assertRedirects(
            respuesta,
            reverse("delegacion_detalle", args=[self.delegacion.pk]),
        )
        self.assertTrue(
            Servicio.objects.filter(
                delegacion=self.delegacion,
                nombre="Retiro de escombros",
                activo=True,
            ).exists()
        )

    def test_no_duplica_servicio_activo(self):
        Servicio.objects.create(delegacion=self.delegacion, nombre="Aseo")
        self.client.force_login(self.supervisor)

        respuesta = self.client.post(
            self.url_crear(), {"nombre": "Aseo"}
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Ya existe un servicio activo")
        self.assertEqual(
            Servicio.objects.filter(
                delegacion=self.delegacion, nombre="Aseo"
            ).count(),
            1,
        )

    def test_crear_reactiva_servicio_dado_de_baja(self):
        inactivo = Servicio.objects.create(
            delegacion=self.delegacion,
            nombre="Aseo",
            activo=False,
        )
        self.client.force_login(self.supervisor)

        self.client.post(self.url_crear(), {"nombre": "Aseo"})

        inactivo.refresh_from_db()
        self.assertTrue(inactivo.activo)
        self.assertEqual(
            Servicio.objects.filter(
                delegacion=self.delegacion, nombre="Aseo"
            ).count(),
            1,
        )

    def test_no_agrega_servicio_a_delegacion_dada_de_baja(self):
        delegacion = Delegacion.objects.create(
            nombre="Delegación Histórica",
            direccion="Calle 1",
            encargado="Sin encargado",
            email="historica@laserena.cl",
            telefono="51 2 000 001",
            celular="",
            activo=False,
        )
        self.client.force_login(self.supervisor)

        respuesta = self.client.post(
            self.url_crear(delegacion), {"nombre": "Aseo"}
        )

        self.assertRedirects(
            respuesta,
            reverse("delegacion_detalle", args=[delegacion.pk]),
        )
        self.assertFalse(
            Servicio.objects.filter(delegacion=delegacion).exists()
        )

    def test_edita_servicio(self):
        servicio = Servicio.objects.create(
            delegacion=self.delegacion, nombre="Aseo"
        )
        self.client.force_login(self.supervisor)

        respuesta = self.client.post(
            reverse("servicio_editar", args=[servicio.pk]),
            {"nombre": "Aseo y ornato"},
        )

        self.assertRedirects(
            respuesta,
            reverse("delegacion_detalle", args=[self.delegacion.pk]),
        )

        servicio.refresh_from_db()
        self.assertEqual(servicio.nombre, "Aseo y ornato")

    def test_baja_y_reactivacion_de_servicio(self):
        servicio = Servicio.objects.create(
            delegacion=self.delegacion, nombre="Aseo"
        )
        self.client.force_login(self.supervisor)

        self.client.post(
            reverse("servicio_cambiar_estado", args=[servicio.pk])
        )
        servicio.refresh_from_db()
        self.assertFalse(servicio.activo)
        self.assertTrue(Servicio.objects.filter(pk=servicio.pk).exists())

        self.client.post(
            reverse("servicio_cambiar_estado", args=[servicio.pk])
        )
        servicio.refresh_from_db()
        self.assertTrue(servicio.activo)

    def test_no_reactiva_servicio_si_la_delegacion_esta_de_baja(self):
        servicio = Servicio.objects.create(
            delegacion=self.delegacion,
            nombre="Aseo",
            activo=False,
        )
        self.delegacion.activo = False
        self.delegacion.save(update_fields=["activo"])

        self.client.force_login(self.supervisor)

        self.client.post(
            reverse("servicio_cambiar_estado", args=[servicio.pk])
        )

        servicio.refresh_from_db()
        self.assertFalse(servicio.activo)

    def test_no_da_de_baja_servicio_con_compromisos_activos(self):
        from tubo_gestionAPP.models import Compromiso

        servicio = Servicio.objects.create(
            delegacion=self.delegacion, nombre="Aseo"
        )
        Compromiso.objects.create(
            tarea="Mejorar luminarias",
            cumplimiento=50,
            delegacion=self.delegacion,
            servicio=servicio,
        )
        self.client.force_login(self.supervisor)

        respuesta = self.client.post(
            reverse("servicio_cambiar_estado", args=[servicio.pk]),
            follow=True,
        )

        self.assertContains(
            respuesta,
            "tiene compromisos activos asignados",
        )

        servicio.refresh_from_db()
        self.assertTrue(servicio.activo)

    def test_reactiva_servicio_sin_compromisos_activos(self):
        from tubo_gestionAPP.models import Compromiso

        servicio = Servicio.objects.create(
            delegacion=self.delegacion,
            nombre="Aseo",
            activo=False,
        )
        Compromiso.objects.create(
            tarea="Compromiso histórico",
            cumplimiento=50,
            delegacion=self.delegacion,
            servicio=servicio,
            activo=False,
        )
        self.client.force_login(self.supervisor)

        self.client.post(
            reverse("servicio_cambiar_estado", args=[servicio.pk])
        )

        servicio.refresh_from_db()
        self.assertTrue(servicio.activo)

    def test_baja_de_servicio_exige_post(self):
        servicio = Servicio.objects.create(
            delegacion=self.delegacion, nombre="Aseo"
        )
        self.client.force_login(self.supervisor)

        respuesta = self.client.get(
            reverse("servicio_cambiar_estado", args=[servicio.pk])
        )

        self.assertEqual(respuesta.status_code, 405)
