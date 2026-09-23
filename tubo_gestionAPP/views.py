import json
import os

from django.shortcuts import render
from django.conf import settings

# Create your views here.
def inicio (request):
    return render(request, 'tubo_gestion/inicio.html')

def tablero_metas(request):
    data_file = os.path.join(settings.BASE_DIR, 'data', 'compromisos.json')
    with open(data_file, encoding='utf-8') as f:
        data = json.load(f)
    return render(request, 'tubo_gestion/tablero_metas.html', {'compromisos': data})