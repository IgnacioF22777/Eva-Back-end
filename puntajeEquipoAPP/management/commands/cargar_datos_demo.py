"""
Carga datos de demostración del SGR (Evaluación 3).

    python manage.py cargar_datos_demo --clave "<clave de las cuentas demo>"
    python manage.py cargar_datos_demo --clave "<clave>" --reiniciar

Crea, sobre las delegaciones reales de La Serena, dos equipos ficticios
(Delegación Centro y Delegación Las Compañías) con funcionarios de cada
cargo de la matriz, y llena el trimestre 2026-T4 con:

- actividades diarias con vecinos, RUT y teléfonos ficticios, respetando el
  máximo de 7 ingresos por día y con distintos niveles de avance (el
  semáforo muestra verde, naranjo y rojo);
- verificación del delegado (aprobadas, pendientes, rechazadas y con
  solicitud de antecedentes) y casos del tubo de seguimiento;
- ausencias (R9), felicitaciones y reclamos con respaldo (R8);
- cartas de Oficina de Partes, atenciones sociales, zonas de riesgo y
  reportes ciudadanos.

Todos los datos son ficticios. Las cuentas demo usan el dominio
@demo.laserena.cl y la clave que se entrega con --clave (nunca queda
escrita en el repositorio). Una de ellas queda con contraseña temporal para
mostrar el cambio obligatorio en el primer ingreso.

Es idempotente: sin --reiniciar no duplica nada; con --reiniciar borra y
vuelve a generar solo los registros de las cuentas demo.
"""

import random
from datetime import date, datetime, time, timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.files.base import ContentFile
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from actividadesAPP.models import ZONA_CHILE, RegistroActividad
from atencionSocialAPP.models import AtencionSocial, SUBTIPOS_POR_TIPO
from delegacionesAPP.models import Delegacion
from emergenciasTerritorialesAPP.models import ZonaRiesgo
from matrizAPP.models import AjusteDesempeno, Ausencia
from oficinaPartesAPP.models import CartaOficinaPartes
from organizacionesAPP.models import OrganizacionComunitaria
from reportesCiudadanosAPP.models import ReporteCiudadano
from seguridadAPP.models import Cargo, PerfilUsuario
from sgr_maestrosAPP.feriados import feriados_entre
from sgr_maestrosAPP.models import Meta, Periodo

User = get_user_model()

DOMINIO = "demo.laserena.cl"
PERIODO = "2026-T4"
CODIGOS_AUTOMATICOS = {"SGR-SOLUCIONES-TUBO", "SGR-EMERGENCIA"}

# (delegación, nombre, apellido, cargo, perfil, factor de avance, rut sin dv)
EQUIPOS = [
    ("Delegación Centro", "Valentina", "Rojas Castillo", "Gestor Social", "Administrativo", 1.20, 16234501),
    ("Delegación Centro", "Matías", "Araya Tapia", "Territorial OO.CC. (Organizaciones Comunitarias)", "Administrativo", 1.00, 17345612),
    ("Delegación Centro", "Francisca", "Cortés Muñoz", "Gestor de Seguridad", "Administrativo", 0.80, 18456723),
    ("Delegación Centro", "Sebastián", "Pizarro Vega", "Coordinador de Servicios Comunitarios", "Administrativo", 0.30, 15567834),
    ("Delegación Centro", "Javiera", "Olivares Díaz", "Gestor Social", "Administrativo", 0.60, 19678945),
    ("Delegación Las Compañías", "Rodrigo", "Castillo Leiva", "Delegado", "Supervisor", 0, 14789056),
    ("Delegación Las Compañías", "Constanza", "Vega Rivera", "Gestor Social", "Administrativo", 0.95, 18890167),
    ("Delegación Las Compañías", "Felipe", "Muñoz Carvajal", "Territorial OO.CC. (Organizaciones Comunitarias)", "Administrativo", 0.65, 17901278),
    ("Delegación Las Compañías", "Daniela", "Tapia Rojas", "Apoyo Administrativo", "Administrativo", 0.40, 16012389),
]
# Funcionaria recién contratada: queda con contraseña temporal.
NUEVA_FUNCIONARIA = "javiera.olivares"

# Cuentas demo ya existentes en el servidor (se completa su cargo).
EXISTENTES = {
    "22456789-8": ("Apoyo Administrativo", 0.80),   # Diego Fuentes, Delegación Centro
}

NOMBRES = [
    "María José Contreras", "Juan Carlos Álvarez", "Rosa Elena Araya", "Luis Alberto Godoy",
    "Carmen Gloria Torres", "Pedro Pablo Cortés", "Ana María Flores", "Jorge Andrés Zepeda",
    "Patricia Alejandra Rivera", "Héctor Manuel Galleguillos", "Claudia Andrea Castillo",
    "Manuel Antonio Rojas", "Verónica Paz Ahumada", "Raúl Eduardo Pastén", "Gladys del Carmen Olivares",
    "Cristián Alejandro Varas", "Margarita Inés Alfaro", "Ricardo Esteban Cortés", "Sonia Beatriz Miranda",
    "Francisco Javier Aguirre", "Isabel Cristina Peralta", "Óscar Iván Carvajal", "Teresa de Jesús Muñoz",
    "Nelson Patricio Barraza", "Elena Margarita Tapia", "Guillermo Andrés Bugueño",
]
SECTORES = {
    "Delegación Centro": ["Barrio Inglés", "Cuatro Esquinas", "Población Arauco", "Villa Alameda", "Plaza de Armas", "Calle Larga"],
    "Delegación Las Compañías": ["Villa El Indio", "Población Gabriela Mistral", "Villa Las Compañías", "El Milagro", "Pedro de Valdivia Norte", "Villa Los Arrayanes"],
}
DETALLES = {
    "SGR-ATENCION-SOCIAL": "Atención presencial por postulación al Registro Social de Hogares en {sector}.",
    "SGR-VISITA-TERRENO": "Visita domiciliaria a adulta mayor en {sector} para evaluar ayuda social.",
    "SGR-ENTREGA-INFORME": "Entrega de informe social para postulación a beneficio municipal ({sector}).",
    "SGR-ENTREGA-BENEFICIO": "Entrega de caja de alimentos y materiales de construcción en {sector}.",
    "SGR-ATENCION-USUARIO": "Atención de vecino por consulta de trámites municipales ({sector}).",
    "SGR-LLAMADAS-PREVENTIVAS": "Llamada preventiva a vecino inscrito en programa de adulto mayor ({sector}).",
    "SGR-INFORME-INVENTARIO": "Informe de inventario de la sede de la delegación.",
    "SGR-INFORME-COMUNICACIONES": "Informe de actividades de la delegación enviado a Comunicaciones.",
    "SGR-REUNIONES-ORGANIZACIONES": "Reunión con la directiva de la junta de vecinos de {sector}.",
    "SGR-CONFORMACION-ORGANIZACIONES": "Asesoría para conformar club de adulto mayor en {sector} (Ley 19.418).",
    "SGR-TALLERES-ACTIVIDADES": "Taller de liderazgo comunitario para dirigentes de {sector}.",
    "SGR-COMITES-SEGURIDAD": "Constitución de comité de seguridad vecinal en {sector}.",
    "SGR-INCIVILIDADES": "Levantamiento de incivilidades (rayados y microbasurales) en {sector}.",
    "SGR-MEDIACION": "Mediación por conflicto de ruidos molestos entre vecinos de {sector}.",
    "SGR-ESPACIOS-PUBLICOS": "Recuperación de plaza con apoyo de vecinos de {sector}.",
    "SGR-INFRACCIONES": "Fiscalización de vehículos abandonados en {sector}.",
    "SGR-SALIDAS-TERRENO": "Ronda preventiva con Seguridad Ciudadana por {sector}.",
    "SGR-INFORMES-PERSONAL": "Informe de asistencia de la cuadrilla de empleabilidad.",
    "SGR-INFORME-TRABAJO": "Informe semanal de trabajos de aseo y ornato.",
    "SGR-OPERATIVO-DELEGACION": "Operativo de limpieza y retiro de voluminosos en {sector}.",
    "SGR-OPERATIVO-DISERCO": "Operativo DISERCO de poda y despeje de luminarias en {sector}.",
    "SGR-TALLERES": "Taller de reciclaje y compostaje para vecinos de {sector}.",
    "SGR-TERRENO": "Inspección en terreno de áreas verdes de {sector}.",
    "SGR-ATENCION-REQUERIMIENTO": "Atención de requerimiento por luminaria apagada en {sector}.",
    "SGR-REUNION-SEMANAL": "Reunión semanal de coordinación del equipo de la delegación.",
    "SGR-SOLUCION-PROBLEMAS": "Solución de problema de acceso a agua potable de vecino de {sector}.",
}
# Actividades que suelen requerir seguimiento hasta su solución.
CON_TUBO = {
    "SGR-ATENCION-SOCIAL", "SGR-ENTREGA-INFORME", "SGR-ATENCION-USUARIO", "SGR-INCIVILIDADES",
    "SGR-MEDIACION", "SGR-ATENCION-REQUERIMIENTO", "SGR-SOLUCION-PROBLEMAS", "SGR-INFRACCIONES",
}


def con_dv(numero):
    suma, factor = 0, 2
    for digito in reversed(str(numero)):
        suma += int(digito) * factor
        factor = 2 if factor == 7 else factor + 1
    resto = 11 - suma % 11
    digito = {11: "0", 10: "K"}.get(resto, str(resto))
    return f"{numero}-{digito}"


class Command(BaseCommand):
    help = "Carga datos de demostración (ficticios) para la Evaluación 3."

    def add_arguments(self, parser):
        parser.add_argument("--clave", help="Clave de las cuentas demo nuevas (obligatoria al crearlas).")
        parser.add_argument("--reiniciar", action="store_true",
                            help="Borra y vuelve a generar los registros de las cuentas demo.")

    def handle(self, *args, **opciones):
        self.azar = random.Random(2026)
        self.hoy = timezone.localdate(timezone.now(), timezone=ZONA_CHILE)

        with transaction.atomic():
            periodo = self.preparar_periodo()
            equipos = self.preparar_equipos(opciones.get("clave"))

            demo = RegistroActividad.objects.filter(funcionario__in=[p for p, _ in equipos])
            if demo.exists() and not opciones["reiniciar"]:
                self.stdout.write(self.style.WARNING(
                    "Ya existen datos demo; use --reiniciar para regenerarlos."
                ))
                return
            if opciones["reiniciar"]:
                self.borrar_demo([p for p, _ in equipos])

            for perfil, factor in equipos:
                if factor:
                    self.generar_actividades(perfil, factor, periodo)
            self.asignar_codigos()
            self.generar_ausencias_y_ajustes(equipos)
            self.generar_cartas_y_atenciones(equipos)
            self.generar_territorio()

        self.stdout.write(self.style.SUCCESS(
            f"Datos demo cargados: {RegistroActividad.objects.filter(funcionario__in=[p for p, _ in equipos]).count()} actividades."
        ))

    # ------------------------------------------------------------
    # PERÍODO Y METAS
    # ------------------------------------------------------------

    def preparar_periodo(self):
        periodo, creado = Periodo.objects.get_or_create(
            codigo=PERIODO,
            defaults={
                "nombre": "Cuarto trimestre 2026",
                "fecha_inicio": date(2026, 10, 1),
                "fecha_fin": date(2026, 12, 31),
            },
        )
        if creado or not Meta.objects.filter(periodo=periodo).exists():
            call_command("cargar_cargos_metas", periodo=PERIODO, stdout=self.stdout)
        return periodo

    # ------------------------------------------------------------
    # EQUIPOS
    # ------------------------------------------------------------

    def preparar_equipos(self, clave):
        equipos = []
        for deleg_nombre, nombre, apellido, cargo_nombre, perfil, factor, numero in EQUIPOS:
            delegacion = Delegacion.objects.get(nombre=deleg_nombre)
            cargo = Cargo.objects.get(nombre=cargo_nombre)
            username = f"{nombre}.{apellido.split()[0]}".lower()
            username = (username.replace("á", "a").replace("é", "e").replace("í", "i")
                        .replace("ó", "o").replace("ú", "u").replace("ñ", "n"))
            usuario = User.objects.filter(username=username).first()
            if usuario is None:
                if not clave:
                    raise CommandError("Indique --clave para crear las cuentas demo.")
                usuario = User.objects.create_user(
                    username=username, password=clave, first_name=nombre, last_name=apellido,
                    email=f"{username}@{DOMINIO}",
                )
            usuario.groups.set([Group.objects.get(name=perfil)])
            perfil_usuario, _ = PerfilUsuario.objects.update_or_create(
                usuario=usuario,
                defaults={
                    "rut": con_dv(numero),
                    "delegacion": delegacion,
                    "cargo": cargo,
                    "debe_cambiar_password": username == NUEVA_FUNCIONARIA,
                },
            )
            equipos.append((perfil_usuario, factor))

        for username, (cargo_nombre, factor) in EXISTENTES.items():
            perfil_usuario = PerfilUsuario.objects.filter(usuario__username=username).first()
            if perfil_usuario:
                perfil_usuario.cargo = Cargo.objects.get(nombre=cargo_nombre)
                perfil_usuario.save(update_fields=["cargo"])
                equipos.append((perfil_usuario, factor))
        return equipos

    def delegado_de(self, perfil):
        supervisor = PerfilUsuario.objects.filter(
            delegacion=perfil.delegacion, usuario__groups__name="Supervisor", usuario__is_active=True,
        ).exclude(pk=perfil.pk).select_related("usuario").first()
        return supervisor.usuario if supervisor else User.objects.filter(is_superuser=True).first()

    def borrar_demo(self, perfiles):
        usuarios = [p.usuario for p in perfiles]
        RegistroActividad.objects.filter(funcionario__in=perfiles).delete()
        Ausencia.objects.filter(funcionario__in=usuarios).delete()
        AjusteDesempeno.objects.filter(funcionario__in=usuarios).delete()
        CartaOficinaPartes.objects.filter(observacion__startswith="[demo]").delete()
        AtencionSocial.objects.filter(detalle__startswith="[demo]").delete()
        ReporteCiudadano.objects.filter(descripcion__startswith="[demo]").delete()
        ZonaRiesgo.objects.filter(descripcion_riesgo__startswith="[demo]").delete()

    # ------------------------------------------------------------
    # ACTIVIDADES, VERIFICACIÓN Y TUBO
    # ------------------------------------------------------------

    def dias_habiles(self, periodo):
        fin = min(periodo.fecha_fin, self.hoy)
        feriados = set(feriados_entre(periodo.fecha_inicio, fin))
        dia, dias = periodo.fecha_inicio, []
        while dia <= fin:
            if dia.weekday() < 5 and dia not in feriados:
                dias.append(dia)
            dia += timedelta(days=1)
        return dias

    def generar_actividades(self, perfil, factor, periodo):
        azar = self.azar
        dias = self.dias_habiles(periodo)
        total_dias = 0
        dia = periodo.fecha_inicio
        while dia <= periodo.fecha_fin:
            total_dias += dia.weekday() < 5
            dia += timedelta(days=1)
        avance_periodo = len(dias) / total_dias

        metas = Meta.objects.filter(periodo=periodo, cargo=perfil.cargo, activo=True).select_related("actividad")
        cupos = {dia: 7 for dia in dias}
        lunes_actual = self.hoy - timedelta(days=self.hoy.weekday())
        delegado = self.delegado_de(perfil)
        sectores = SECTORES.get(perfil.delegacion.nombre, ["La Serena"])
        nuevos = []

        for meta in metas:
            codigo = meta.actividad.codigo
            if codigo in CODIGOS_AUTOMATICOS:
                continue
            cantidad = round(float(meta.valor_objetivo) * avance_periodo * factor * azar.uniform(0.9, 1.15))
            cantidad = max(cantidad, 1 if factor >= 0.5 else 0)
            for _ in range(cantidad):
                disponibles = [d for d in dias if cupos[d] > 0]
                if not disponibles:
                    break
                fecha = azar.choice(disponibles)
                cupos[fecha] -= 1
                nuevos.append(self.armar_registro(
                    perfil, meta.actividad, fecha, azar.choice(sectores), lunes_actual, delegado,
                ))

        # Emergencias atendidas (meta automática «Emergencia»).
        emergencia = Meta.objects.filter(periodo=periodo, cargo=perfil.cargo,
                                         actividad__codigo="SGR-EMERGENCIA").first()
        for _ in range(azar.randint(0, 2) if emergencia else 0):
            disponibles = [d for d in dias if cupos[d] > 0]
            if disponibles:
                fecha = azar.choice(disponibles)
                cupos[fecha] -= 1
                registro = self.armar_registro(perfil, emergencia.actividad, fecha,
                                               azar.choice(sectores), lunes_actual, delegado)
                registro.detalle = f"Emergencia: anegamiento de vivienda por lluvia en {azar.choice(sectores)}."
                registro.ingresa_tubo = True
                registro.es_emergencia = True
                nuevos.append(registro)

        RegistroActividad.objects.bulk_create(nuevos, batch_size=300)

    def armar_registro(self, perfil, actividad, fecha, sector, lunes_actual, delegado):
        azar = self.azar
        nombre = azar.choice(NOMBRES)
        sin_telefono = azar.random() < 0.04
        es_delegado = azar.random() < 0.02
        ingreso = datetime.combine(fecha, time(azar.randint(9, 17), azar.randint(0, 59)), tzinfo=ZONA_CHILE)

        registro = RegistroActividad(
            funcionario=perfil,
            actividad=actividad,
            fecha_actividad=fecha,
            fecha_ingreso=ingreso,
            solicitante_tipo=RegistroActividad.TIPO_DELEGADO if es_delegado else RegistroActividad.TIPO_VECINO,
            nombre_usuario=perfil.delegacion.encargado if es_delegado else nombre,
            telefono_usuario="" if sin_telefono else f"9{azar.randint(10000000, 99999999)}",
            rut_usuario=con_dv(azar.randint(6000000, 22000000)) if azar.random() < 0.6 else "",
            detalle=DETALLES.get(actividad.codigo, "Gestión realizada en {sector}.").format(sector=sector),
        )
        registro.actualizar_puntaje()

        if actividad.codigo in CON_TUBO and azar.random() < 0.35:
            registro.ingresa_tubo = True
            antiguedad = (self.hoy - fecha).days
            if antiguedad > 14:
                registro.estado_tubo = azar.choices(
                    [RegistroActividad.TUBO_SOLUCIONADO, RegistroActividad.TUBO_DERIVADO,
                     RegistroActividad.TUBO_EN_PROCESO, RegistroActividad.TUBO_NO_APLICA],
                    weights=[78, 10, 9, 3],
                )[0]
            else:
                registro.estado_tubo = azar.choice(
                    [RegistroActividad.TUBO_EN_PROCESO, RegistroActividad.TUBO_SOLUCIONADO])
            if registro.estado_tubo == RegistroActividad.TUBO_SOLUCIONADO:
                registro.fecha_solucion = min(fecha + timedelta(days=azar.randint(1, 12)), self.hoy)

        if fecha < lunes_actual:
            estado = azar.choices(
                [RegistroActividad.APROBADA, RegistroActividad.ANTECEDENTES,
                 RegistroActividad.RECHAZADA, RegistroActividad.PENDIENTE],
                weights=[86, 5, 3, 6],
            )[0]
            registro.estado_verificacion = estado
            if estado != RegistroActividad.PENDIENTE:
                registro.verificado_por = delegado
                registro.fecha_verificacion = ingreso + timedelta(days=azar.randint(1, 3))
                registro.observacion_verificacion = {
                    RegistroActividad.ANTECEDENTES: "Adjuntar acta o fotografía de la actividad.",
                    RegistroActividad.RECHAZADA: "La gestión no corresponde al cargo: registrar como otra gestión.",
                }.get(estado, "")
        return registro

    def asignar_codigos(self):
        for registro in RegistroActividad.objects.filter(codigo__isnull=True).only("pk", "fecha_ingreso"):
            registro.asignar_codigo()

    # ------------------------------------------------------------
    # AUSENCIAS, FELICITACIONES Y RECLAMOS
    # ------------------------------------------------------------

    def generar_ausencias_y_ajustes(self, equipos):
        por_usuario = {p.usuario.username: p for p, _ in equipos}

        def ausencia(username, tipo, inicio, fin, obs):
            perfil = por_usuario.get(username)
            if perfil:
                Ausencia.objects.create(
                    funcionario=perfil.usuario, delegacion=perfil.delegacion, tipo=tipo,
                    fecha_inicio=inicio, fecha_fin=fin, observacion=obs,
                    registrado_por=self.delegado_de(perfil),
                )

        ausencia("valentina.rojas", "VACACIONES", date(2026, 10, 19), date(2026, 10, 23), "Feriado legal.")
        ausencia("sebastian.pizarro", "LICENCIA", date(2026, 11, 3), date(2026, 11, 6), "Licencia médica.")
        ausencia("daniela.tapia", "ADMINISTRATIVO", date(2026, 10, 30), date(2026, 10, 30), "Día administrativo.")

        def ajuste(username, tipo, fecha, medio, remitente, contacto, descripcion):
            perfil = por_usuario.get(username)
            if not perfil:
                return
            registro = AjusteDesempeno(
                funcionario=perfil.usuario, delegacion=perfil.delegacion, tipo=tipo, fecha=fecha,
                medio=medio, remitente_nombre=remitente, remitente_contacto=contacto,
                descripcion=descripcion, registrado_por=self.delegado_de(perfil),
            )
            contenido = (
                "%PDF-1.4\n% Respaldo de demostración (ficticio)\n"
                f"% {tipo} recibida el {fecha:%d/%m/%Y} por {medio}\n%%EOF\n"
            ).encode()
            nombre_archivo = f"respaldo_{tipo.lower()}.pdf"
            registro.respaldo.save(nombre_archivo, ContentFile(contenido), save=False)
            registro.nombre_original = nombre_archivo
            registro.save()

        ajuste("valentina.rojas", AjusteDesempeno.FELICITACION, date(2026, 10, 28), "CORREO_DELEGADO",
               "Gladys Olivares", "gladys.olivares@correo.cl",
               "Agradece la gestión rápida del subsidio de agua potable para su madre.")
        ajuste("matias.araya", AjusteDesempeno.FELICITACION, date(2026, 11, 12), "CARTA_DELEGACION",
               "JJVV Barrio Inglés", "912345001",
               "La directiva destaca el apoyo en la renovación de su personalidad jurídica.")
        ajuste("sebastian.pizarro", AjusteDesempeno.RECLAMO, date(2026, 11, 10), "LIBRO_OBSERVACIONES",
               "Raúl Pastén", "987650002",
               "Operativo de retiro de voluminosos no se realizó en la fecha comprometida.")

    # ------------------------------------------------------------
    # CARTAS Y ATENCIÓN SOCIAL
    # ------------------------------------------------------------

    def generar_cartas_y_atenciones(self, equipos):
        azar = self.azar
        temas = [
            "Solicitud de reposición de luminarias en pasaje.",
            "Solicitud de poda de árboles que interfieren el tendido eléctrico.",
            "Solicitud de operativo de limpieza de microbasural.",
            "Solicitud de uso de sede social para actividad navideña.",
            "Solicitud de reductores de velocidad frente a escuela.",
            "Invitación a la alcaldesa a aniversario de la junta de vecinos.",
            "Solicitud de apoyo para mejoramiento de multicancha.",
            "Solicitud de camión aljibe para sector sin agua potable.",
        ]
        delegaciones = {p.delegacion for p, _ in equipos}
        for delegacion in delegaciones:
            organizaciones = list(
                OrganizacionComunitaria.objects.filter(delegacion=delegacion).values_list("nombre", flat=True)[:40]
            ) or [f"Junta de Vecinos {s}" for s in SECTORES.get(delegacion.nombre, ["La Serena"])]
            encargados = [p.usuario.get_full_name() for p, _ in equipos if p.delegacion == delegacion]
            for numero in range(1, 11):
                recibida = self.hoy - timedelta(days=azar.randint(2, 50))
                estado = azar.choices(
                    [CartaOficinaPartes.EN_PROCESO, CartaOficinaPartes.APROBADA,
                     CartaOficinaPartes.FINALIZADA, CartaOficinaPartes.NO_APLICA],
                    weights=[35, 20, 40, 5],
                )[0]
                carta = CartaOficinaPartes(
                    delegacion=delegacion, fecha_recepcion=recibida,
                    numero_ingreso=f"OP-{recibida:%y%m}-{numero:03d}",
                    destinatario=azar.choice([CartaOficinaPartes.ALCALDESA, CartaOficinaPartes.DELEGADO]),
                    remitente=azar.choice(organizaciones)[:150],
                    telefono_contacto=f"9{azar.randint(10000000, 99999999)}",
                    tema=azar.choice(temas),
                    encargado_seguimiento=azar.choice(encargados)[:100],
                    estado=estado,
                    observacion="[demo] Carta ficticia de demostración.",
                )
                carta.save()

            for _ in range(14):
                tipo = azar.choice(["INFORME", "SUBSIDIO", "SUBSIDIO", "DERIVACION", "OTRA"])
                subtipos = sorted(SUBTIPOS_POR_TIPO[tipo])
                AtencionSocial.objects.create(
                    delegacion=delegacion,
                    fecha=self.hoy - timedelta(days=azar.randint(0, 45)),
                    tipo=tipo,
                    subtipo=azar.choice(subtipos) if subtipos else "",
                    nombre_vecino=azar.choice(NOMBRES),
                    telefono_vecino=f"9{azar.randint(10000000, 99999999)}",
                    derivada_a="CESFAM Cardenal Caro" if tipo == "DERIVACION" else "",
                    detalle="[demo] Atención ficticia de demostración.",
                )

    # ------------------------------------------------------------
    # ZONAS DE RIESGO Y REPORTES CIUDADANOS
    # ------------------------------------------------------------

    def generar_territorio(self):
        centro = Delegacion.objects.get(nombre="Delegación Centro")
        companias = Delegacion.objects.get(nombre="Delegación Las Compañías")
        zonas = [
            (centro, "Quebrada San Francisco", "alto", "[demo] Riesgo de remoción en masa con lluvias intensas."),
            (centro, "Borde costero Av. del Mar norte", "medio", "[demo] Zona de inundación por tsunami."),
            (companias, "Cauce río Elqui sector El Milagro", "critico", "[demo] Desborde del río en eventos de crecida."),
        ]
        for delegacion, nombre, nivel, descripcion in zonas:
            ZonaRiesgo.objects.get_or_create(
                nombre=nombre, delegacion=delegacion,
                defaults={"nivel_peligro": nivel, "descripcion_riesgo": descripcion},
            )
        reportes = [
            (centro, "alumbrado", "alta", "Calle Cordovez con Colón", "Tres luminarias apagadas en la cuadra."),
            (centro, "basura", "media", "Plaza Buenos Aires", "Microbasural en esquina de la plaza."),
            (companias, "baches", "alta", "Av. Los Arrayanes 2300", "Bache profundo frente a paradero."),
            (companias, "verde", "baja", "Plaza Villa El Indio", "Riego automático sin funcionar."),
            (companias, "seguridad", "media", "Pasaje Los Olivos", "Vecinos solicitan mayor patrullaje nocturno."),
        ]
        for delegacion, tipo, prioridad, ubicacion, descripcion in reportes:
            ReporteCiudadano.objects.get_or_create(
                delegacion=delegacion, ubicacion=ubicacion,
                defaults={
                    "tipo": tipo, "prioridad": prioridad,
                    "descripcion": f"[demo] {descripcion}",
                    "nombre_vecino": self.azar.choice(NOMBRES),
                    "telefono_vecino": f"9{self.azar.randint(10000000, 99999999)}",
                },
            )
