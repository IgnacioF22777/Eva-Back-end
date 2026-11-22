
"""
CP-ASG-025: Validación de permisos al anular asignaciones.
"""

from rest_framework.test import APITestCase

from delegacionesAPP.models import Delegacion, Servicio
from seguridadAPP.perfiles import ADMINISTRADOR, SUPERVISOR
from seguridadAPP.roles import sincronizar_roles

from .models import AsignacionCompromiso, Compromiso
from .tests import crear_usuario


class PruebasAnulacionAmbito(APITestCase):

    @classmethod
    def setUpTestData(cls):
        sincronizar_roles()

        cls.centro = Delegacion.objects.create(
            nombre="Delegación Centro",
            direccion="Dirección Centro",
            encargado="Encargado Centro",
            email="centro@example.com",
            telefono="512000000",
            celular="+56911111111",
        )

        cls.rural = Delegacion.objects.create(
            nombre="Delegación Rural",
            direccion="Dirección Rural",
            encargado="Encargado Rural",
            email="rural@example.com",
            telefono="512000001",
            celular="+56922222222",
        )

        cls.servicio_centro = Servicio.objects.create(
            delegacion=cls.centro,
            nombre="Trámites",
        )

        cls.servicio_rural = Servicio.objects.create(
            delegacion=cls.rural,
            nombre="Riego",
        )

        cls.admin = crear_usuario(
            "13.333.333-3",
            "admin.ambito@example.com",
            ADMINISTRADOR,
        )

        cls.supervisor = crear_usuario(
            "14.444.444-4",
            "supervisor.ambito@example.com",
            SUPERVISOR,
            delegacion=cls.centro,
        )

    def setUp(self):
        self.compromiso = Compromiso.objects.create(
            tarea="Prueba de seguridad territorial",
            cumplimiento=0,
        )

    def asignar_como_admin(self, delegacion, servicio):
        self.client.force_authenticate(user=self.admin)

        respuesta = self.client.post(
            "/api/asignaciones/",
            {
                "compromiso": self.compromiso.pk,
                "delegacion": delegacion.pk,
                "servicio": servicio.pk,
                "observacion": "Asignación de prueba",
            },
            format="json",
        )

        self.assertEqual(respuesta.status_code, 201)
        return respuesta.data["id"]

    def test_cp_asg_025_supervisor_no_restaura_delegacion_ajena(self):
        """
        Un supervisor de Centro no debe poder anular una asignación
        si eso devuelve el compromiso a Rural.
        """

        anterior_id = self.asignar_como_admin(
            self.rural,
            self.servicio_rural,
        )

        actual_id = self.asignar_como_admin(
            self.centro,
            self.servicio_centro,
        )

        self.client.force_authenticate(user=self.supervisor)

        respuesta = self.client.delete(
            f"/api/asignaciones/{actual_id}/",
            {"motivo": "Asignación equivocada"},
            format="json",
        )

        # El cambio hacia otra delegación debe rechazarse.
        self.assertEqual(respuesta.status_code, 403)

        self.compromiso.refresh_from_db()

        # No debe modificarse el compromiso ni su historial.
        self.assertEqual(
            self.compromiso.delegacion_id,
            self.centro.pk,
        )

        actual = AsignacionCompromiso.objects.get(pk=actual_id)
        anterior = AsignacionCompromiso.objects.get(pk=anterior_id)

        self.assertTrue(actual.activo)
        self.assertFalse(actual.anulada)
        self.assertFalse(anterior.activo)
