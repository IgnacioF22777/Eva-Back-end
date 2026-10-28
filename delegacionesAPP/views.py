from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from .models import Delegacion


@login_required
def delegaciones(request):
    data = Delegacion.objects.all().prefetch_related('servicios')
    return render(request, 'delegaciones/lista_delegaciones.html', {'delegaciones': data})


@login_required
def inicio(request):
    data = Delegacion.objects.all()
    return render(request, 'delegaciones/inicio.html', {'delegaciones': data})
