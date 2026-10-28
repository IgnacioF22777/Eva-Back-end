from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from .models import Compromiso


# Create your views here.
@login_required
def inicio(request):
    return render(request, 'tubo_gestion/inicio.html')


@login_required
def tablero_metas(request):
    data = Compromiso.objects.all()
    return render(request, 'tubo_gestion/tablero_metas.html', {'compromisos': data})
