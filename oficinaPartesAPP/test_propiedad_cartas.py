"""
Evaluación 3 - Tubo de cartas: propiedad del registro.

Pauta, Actividad 1: «Todos los funcionarios de la delegación pueden
consultar el Tubo, pero cada funcionario solo puede modificar sus propios
registros mientras no estén aprobados».

Casos CP-CTP-001 a CP-CTP-006.
"""
from django.urls import reverse

from seguridadAPP.perfiles import ADMINISTRATIVO
from tubo_gestionAPP.tests import crear_usuario

from .models import CartaOficinaPartes
from .tests import BaseCartas


class PruebasPropiedadCartas(BaseCartas):

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.companero = crear_usuario("13.333.333-3", "comp@laserena.cl", ADMINISTRATIVO, delegacion=cls.centro)

    def editar(self, carta, usuario, **cambios):
        self.client.force_login(usuario)
        return self.client.post(
            reverse("oficina_partes:carta_editar", args=[carta.pk]),
            self.datos(**cambios),
        )

    def test_cp_ctp_001_funcionario_modifica_su_carta_en_proceso(self):
        carta = self.carta(registrada_por=self.administrativo)
        respuesta = self.editar(carta, self.administrativo, tema="Tema corregido")
        self.assertRedirects(respuesta, reverse("oficina_partes:carta_lista"))
        carta.refresh_from_db()
        self.assertEqual(carta.tema, "Tema corregido")

    def test_cp_ctp_002_no_modifica_la_carta_de_un_companero(self):
        carta = self.carta(registrada_por=self.companero)
        respuesta = self.editar(carta, self.administrativo, tema="Intento")
        self.assertEqual(respuesta.status_code, 403)
        carta.refresh_from_db()
        self.assertNotEqual(carta.tema, "Intento")

    def test_cp_ctp_003_no_modifica_su_carta_ya_aprobada(self):
        carta = self.carta(registrada_por=self.administrativo, estado=CartaOficinaPartes.APROBADA)
        self.assertEqual(self.editar(carta, self.administrativo).status_code, 403)

    def test_cp_ctp_004_todos_consultan_el_tubo_de_la_delegacion(self):
        self.carta(registrada_por=self.companero, remitente="Club Deportivo Las Rojas")
        self.client.force_login(self.administrativo)
        respuesta = self.client.get(reverse("oficina_partes:carta_lista"))
        self.assertContains(respuesta, "Club Deportivo Las Rojas")
        # La ve, pero sin el botón de seguimiento.
        self.assertNotContains(respuesta, "Seguimiento</a>")

    def test_cp_ctp_005_el_delegado_hace_seguimiento_de_todas(self):
        carta = self.carta(registrada_por=self.companero, estado=CartaOficinaPartes.APROBADA)
        respuesta = self.editar(carta, self.supervisor, estado="FINALIZADA")
        self.assertRedirects(respuesta, reverse("oficina_partes:carta_lista"))

    def test_cp_ctp_006_lista_muestra_seguimiento_solo_en_las_propias(self):
        propia = self.carta(registrada_por=self.administrativo)
        ajena = self.carta(registrada_por=self.companero)
        self.client.force_login(self.administrativo)
        respuesta = self.client.get(reverse("oficina_partes:carta_lista"))
        self.assertContains(respuesta, reverse("oficina_partes:carta_editar", args=[propia.pk]))
        self.assertNotContains(respuesta, reverse("oficina_partes:carta_editar", args=[ajena.pk]))
