import json
import os

from django.shortcuts import render
from django.conf import settings


def delegaciones(request):
    data_file = os.path.join(settings.BASE_DIR, 'data', 'delegaciones.json')
    with open(data_file, encoding='utf-8') as f:
        data = json.load(f)
    return render(request, 'delegaciones/lista_delegaciones.html', {'delegaciones': data})


def inicio(request):
    data_file = os.path.join(settings.BASE_DIR, 'data', 'delegaciones.json')
    with open(data_file, encoding='utf-8') as f:
        data = json.load(f)
    return render(request, 'delegaciones/inicio.html', {'delegaciones': data})