from django.core.management.base import BaseCommand, CommandError

from organizacionesAPP.importacion import ArchivoInvalido, importar, leer_xlsx


class Command(BaseCommand):
    help = (
        "Importa el registro de juntas de vecinos y organizaciones "
        "comunitarias desde la planilla municipal (.xlsx). Se puede ejecutar "
        "varias veces sin duplicar."
    )

    def add_arguments(self, parser):
        parser.add_argument("archivo", help="Ruta de la planilla .xlsx.")
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Muestra el resultado sin guardar cambios.",
        )

    def handle(self, *args, **opciones):
        try:
            filas = leer_xlsx(opciones["archivo"])
        except ArchivoInvalido as error:
            raise CommandError(str(error))

        resumen = importar(filas, simular=opciones["dry_run"])

        titulo = "SIMULACIÓN (no se guardó nada)" if opciones["dry_run"] else "Importación completada"
        self.stdout.write(self.style.SUCCESS(f"{titulo}: {resumen.leidas} filas leídas."))
        self.stdout.write(
            f"  {resumen.creadas} creadas, {resumen.actualizadas} actualizadas, "
            f"{resumen.sin_cambios} sin cambios, {resumen.protegidas} verificadas "
            f"(no se modifican), {len(resumen.omitidas)} omitidas."
        )

        for tipo, cantidad in resumen.advertencias.most_common():
            self.stdout.write(self.style.WARNING(
                f"  Aviso: {cantidad} con {tipo} (ej.: {resumen.ejemplos[tipo]})"
            ))

        for omitida in resumen.omitidas[:20]:
            self.stdout.write(self.style.ERROR(f"  Omitida: {omitida}"))
        if len(resumen.omitidas) > 20:
            self.stdout.write(self.style.ERROR(
                f"  … y {len(resumen.omitidas) - 20} filas omitidas más."
            ))
