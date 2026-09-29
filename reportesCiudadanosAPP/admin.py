from django.contrib import admin
from .models import ReporteCiudadano

@admin.register(ReporteCiudadano)
class ReporteCiudadanoAdmin(admin.ModelAdmin):
    list_display = ('tipo', 'delegacion', 'prioridad', 'estado', 'fecha_reporte')
    list_filter = ('estado', 'prioridad', 'tipo', 'delegacion')
    search_fields = ('descripcion', 'ubicacion')
    date_hierarchy = 'fecha_reporte'
    
    fieldsets = (
        ('Información General', {
            'fields': ('delegacion', 'tipo', 'prioridad', 'estado')
        }),
        ('Detalles del Reporte', {
            'fields': ('descripcion', 'ubicacion')
        }),
        ('Tiempos', {
            'fields': ('fecha_reporte', 'fecha_resolucion'),
        }),
    )
    readonly_fields = ('fecha_reporte',)
