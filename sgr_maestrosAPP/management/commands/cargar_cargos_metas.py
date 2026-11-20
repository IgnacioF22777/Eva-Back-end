import json
from decimal import Decimal
from pathlib import Path

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from seguridadAPP.models import Cargo
from sgr_maestrosAPP.models import CatalogoActividad, Meta, Periodo
from tubo_gestionAPP.validadores import TIPO_GESTION_EJECUCION


ARCHIVO_POR_DEFECTO = (
    Path(__file__).resolve().parents[2] / "datos" / "matriz_sgr_2026_t3.json"
)


# ============================================================
# CARGA DE LOS 8 CARGOS Y SUS METAS REALES (EVALUACIÓN 3)
# ============================================================
# Lee los cargos del descriptor de funciones y las metas trimestrales de
# la matriz SGR desde un archivo JSON y los deja en la base de datos.
#
# Es idempotente: correrlo varias veces deja el mismo resultado. Los
# registros se buscan por su clave natural (código de actividad, nombre
# del cargo, código de período y código de meta), se crean si faltan y se
# actualizan si cambiaron. Todo ocurre en una sola transacción: si una
# meta no cumple las reglas del modelo, no se guarda nada.


class Command(BaseCommand):
    help = (
        "Carga los 8 cargos del descriptor de funciones y sus metas reales "
        "de la matriz SGR. Se puede ejecutar varias veces sin duplicar."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--archivo",
            default=str(ARCHIVO_POR_DEFECTO),
            help="Archivo JSON con cargos, actividades y metas.",
        )
        parser.add_argument(
            "--periodo",
            help=(
                "Código de un período existente donde cargar las metas. Por "
                "defecto se usa (o se crea) el período definido en el archivo."
            ),
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Muestra lo que haría sin guardar cambios.",
        )

    # ------------------------------------------------------------------
    def handle(self, *args, **opciones):
        datos = self.leer_archivo(opciones["archivo"])
        self.conteo = {}

        try:
            with transaction.atomic():
                actividades = self.cargar_actividades(datos["actividades"])
                cargos = self.cargar_cargos(datos["cargos"])
                periodo = self.obtener_periodo(datos["periodo"], opciones["periodo"])
                self.cargar_metas(datos["cargos"], cargos, actividades, periodo)

                if opciones["dry_run"]:
                    transaction.set_rollback(True)
        except ValidationError as error:
            raise CommandError(
                "No se guardó ningún cambio. " + "; ".join(error.messages)
            )

        self.informar(datos, cargos, periodo, opciones["dry_run"])

    # ------------------------------------------------------------------
    def leer_archivo(self, ruta):
        try:
            datos = json.loads(Path(ruta).read_text(encoding="utf-8"))
        except FileNotFoundError:
            raise CommandError(f"No existe el archivo {ruta}.")
        except json.JSONDecodeError as error:
            raise CommandError(f"El archivo {ruta} no es un JSON válido: {error}")

        faltantes = {"periodo", "actividades", "cargos"} - set(datos)
        if faltantes:
            raise CommandError(
                "Al archivo le faltan las secciones: " + ", ".join(sorted(faltantes))
            )

        codigos = {a["codigo"] for a in datos["actividades"]}
        for cargo in datos["cargos"]:
            for meta in cargo["metas"]:
                if meta["actividad"] not in codigos:
                    raise CommandError(
                        f"La meta de {cargo['nombre']} usa la actividad "
                        f"{meta['actividad']}, que no está en el archivo."
                    )
        return datos

    def contar(self, entidad, resultado):
        self.conteo.setdefault(entidad, {"creados": 0, "actualizados": 0, "sin cambios": 0})
        self.conteo[entidad][resultado] += 1

    def guardar(self, entidad, objeto, valores):
        """Crea o actualiza `objeto` con `valores` y lo valida antes."""
        nuevo = objeto.pk is None
        cambios = [k for k, v in valores.items() if getattr(objeto, k) != v]

        if not nuevo and not cambios:
            self.contar(entidad, "sin cambios")
            return objeto

        for campo, valor in valores.items():
            setattr(objeto, campo, valor)

        objeto.full_clean()
        objeto.save()
        self.contar(entidad, "creados" if nuevo else "actualizados")
        return objeto

    # ------------------------------------------------------------------
    def cargar_actividades(self, filas):
        actividades = {}

        for fila in filas:
            actividad = (
                CatalogoActividad.objects.filter(codigo__iexact=fila["codigo"]).first()
                or CatalogoActividad(codigo=fila["codigo"])
            )
            valores = {
                "nombre": fila["nombre"],
                "activo": True,
            }
            if actividad.pk is None:
                # Solo al crear: no se pisa lo que el usuario edite después.
                valores.update({
                    "area": "Matriz SGR",
                    "tipo_gestion": TIPO_GESTION_EJECUCION,
                    "descripcion": fila.get("automatica", ""),
                })
            actividades[fila["codigo"]] = self.guardar("Actividades", actividad, valores)

        return actividades

    def cargar_cargos(self, filas):
        cargos = {}

        for fila in filas:
            cargo = (
                Cargo.objects.filter(nombre__iexact=fila["nombre"]).first()
                or Cargo(nombre=fila["nombre"])
            )
            valores = {"activo": True}
            if cargo.pk is None or not cargo.descripcion:
                valores["descripcion"] = fila["descripcion"]
            cargos[fila["sigla"]] = self.guardar("Cargos", cargo, valores)

        return cargos

    def obtener_periodo(self, datos_periodo, codigo_elegido):
        if codigo_elegido:
            periodo = Periodo.objects.filter(codigo__iexact=codigo_elegido).first()
            if periodo is None:
                raise CommandError(f"No existe el período {codigo_elegido}.")
        else:
            periodo = Periodo.objects.filter(
                codigo__iexact=datos_periodo["codigo"]
            ).first()

            if periodo is None:
                periodo = Periodo(
                    codigo=datos_periodo["codigo"],
                    nombre=datos_periodo["nombre"],
                    fecha_inicio=datos_periodo["fecha_inicio"],
                    fecha_fin=datos_periodo["fecha_fin"],
                )
                periodo.full_clean()
                periodo.save()
                self.contar("Períodos", "creados")
            else:
                self.contar("Períodos", "sin cambios")

        if periodo.cerrado:
            raise CommandError(
                f"El período {periodo.codigo} está cerrado: no se le pueden "
                "cargar metas."
            )
        return periodo

    def cargar_metas(self, filas_cargos, cargos, actividades, periodo):
        for fila in filas_cargos:
            if not fila["metas"]:
                continue

            cargo = cargos[fila["sigla"]]
            prefijo = f"{periodo.codigo}-{fila['sigla']}-"

            # Foto de las metas de esta carga antes de tocarlas, para informar
            # después si realmente cambiaron.
            campos = ("nombre", "periodo_id", "actividad_id", "cargo_id",
                      "valor_objetivo", "ponderacion", "activo")
            previas = {
                m["codigo"].upper(): tuple(m[c] for c in campos)
                for m in Meta.objects.filter(codigo__istartswith=prefijo).values("codigo", *campos)
            }

            # Las metas de esta carga se desactivan antes de volver a
            # validarlas: así la suma de ponderaciones del cargo se calcula
            # desde cero y no choca con los valores anteriores.
            Meta.objects.filter(codigo__istartswith=prefijo).update(activo=False)

            for numero, datos_meta in enumerate(fila["metas"], start=1):
                codigo = f"{prefijo}{numero:02d}"
                actividad = actividades[datos_meta["actividad"]]
                meta = Meta.objects.filter(codigo__iexact=codigo).first() or Meta(codigo=codigo)
                nueva = meta.pk is None

                meta.nombre = actividad.nombre
                meta.periodo = periodo
                meta.actividad = actividad
                meta.cargo = cargo
                meta.valor_objetivo = Decimal(datos_meta["valor_objetivo"])
                meta.ponderacion = Decimal(datos_meta["ponderacion"])
                meta.activo = True
                if nueva:
                    meta.descripcion = (
                        f"Meta trimestral de {cargo.nombre} según la matriz SGR."
                    )

                try:
                    meta.full_clean()
                except ValidationError as error:
                    raise ValidationError(
                        f"Meta {codigo} ({cargo.nombre}): " + "; ".join(error.messages)
                    )
                meta.save()

                if nueva:
                    self.contar("Metas", "creados")
                elif previas.get(codigo.upper()) == tuple(getattr(meta, c) for c in campos):
                    self.contar("Metas", "sin cambios")
                else:
                    self.contar("Metas", "actualizados")

    # ------------------------------------------------------------------
    def informar(self, datos, cargos, periodo, simulado):
        titulo = "SIMULACIÓN (no se guardó nada)" if simulado else "Carga completada"
        self.stdout.write(self.style.SUCCESS(f"{titulo} en el período {periodo.codigo}."))

        for entidad, conteo in self.conteo.items():
            self.stdout.write(
                f"  {entidad}: {conteo['creados']} creados, "
                f"{conteo['actualizados']} actualizados, "
                f"{conteo['sin cambios']} sin cambios"
            )

        for fila in datos["cargos"]:
            if not fila["metas"]:
                self.stdout.write(self.style.WARNING(
                    f"  Aviso: {fila['nombre']} no tiene metas en la matriz."
                ))
                continue

            suma = sum(Decimal(m["ponderacion"]) for m in fila["metas"])
            if suma != 100:
                self.stdout.write(self.style.WARNING(
                    f"  Aviso: las metas de {fila['nombre']} suman {suma}%. "
                    "El período no se podrá cerrar hasta que este cargo sume 100%."
                ))

        for diferencia in datos.get("diferencias_por_persona", []):
            self.stdout.write(self.style.WARNING(f"  Diferencia en la matriz: {diferencia}"))
