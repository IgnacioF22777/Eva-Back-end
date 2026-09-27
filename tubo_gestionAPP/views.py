from django.shortcuts import render
from .models import Compromiso

# Create your views here.
def inicio (request):
    return render(request, 'tubo_gestion/inicio.html')

def tablero_metas(request):
    data = Compromiso.objects.all()
    return render(request, 'tubo_gestion/tablero_metas.html', {'compromisos': data})
