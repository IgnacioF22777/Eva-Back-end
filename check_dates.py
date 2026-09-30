from reportesCiudadanosAPP.models import ReporteCiudadano
for r in ReporteCiudadano.objects.all():
    print(f"ID: {r.id}, Fecha: {r.fecha_reporte}")
