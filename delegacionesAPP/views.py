from django.shortcuts import render
from .models import Delegacion

def delegaciones(request):
    data = Delegacion.objects.all().prefetch_related('servicios')
    return render(request, 'delegaciones/lista_delegaciones.html', {'delegaciones': data})


def inicio(request):
    data = Delegacion.objects.all()
    return render(request, 'delegaciones/inicio.html', {'delegaciones': data})
