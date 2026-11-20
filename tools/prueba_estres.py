"""
Prueba de estrés del SGR: N usuarios simultáneos navegando el sistema.

Cada usuario virtual abre su propia sesión, inicia sesión (con token CSRF,
como un navegador) y recorre varias veces las pantallas principales. Al
final informa solicitudes, errores, solicitudes por segundo y tiempos de
respuesta (mediana, p90, p95 y máximo) por pantalla.

Solo usa la biblioteca estándar de Python. Ejemplo:

    set SGR_ESTRES_USUARIO=<RUT o usuario de prueba>
    set SGR_ESTRES_CLAVE=<contraseña>
    python tools/prueba_estres.py --url http://44.217.180.71 --usuarios 50 --vueltas 5

Las credenciales se leen de variables de entorno para que no queden en el
historial de la consola ni en el repositorio. Usa una cuenta de prueba, no
una cuenta real, y avisa al equipo antes de estresar el servidor.
"""
import argparse
import http.cookiejar
import json
import os
import re
import statistics
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

PANTALLAS = [
    ("Panel", "/seguridad/panel/"),
    ("Delegaciones", "/delegaciones/"),
    ("Tubo de compromisos", "/gestion/compromisos/"),
    ("Catálogo", "/maestros/catalogo/"),
    ("Metas", "/maestros/metas/"),
    ("Organizaciones", "/organizaciones/?delegacion="),
    ("Cartas", "/oficina-partes/"),
]

UMBRAL_P95 = 2.0  # segundos

resultados = defaultdict(list)   # pantalla -> [segundos]
errores = defaultdict(list)      # pantalla -> [detalle]
candado = threading.Lock()


def registrar(pantalla, segundos, error=None):
    with candado:
        resultados[pantalla].append(segundos)
        if error:
            errores[pantalla].append(error)


def pedir(abridor, url, datos=None, referer=None):
    cuerpo = urllib.parse.urlencode(datos).encode() if datos else None
    solicitud = urllib.request.Request(url, data=cuerpo, headers={
        "User-Agent": "SGR-prueba-estres/1.0",
        **({"Referer": referer} if referer else {}),
    })
    inicio = time.perf_counter()
    try:
        with abridor.open(solicitud, timeout=30) as respuesta:
            contenido = respuesta.read()
            return respuesta.status, respuesta.geturl(), contenido, time.perf_counter() - inicio
    except urllib.error.HTTPError as error:
        return error.code, url, b"", time.perf_counter() - inicio
    except Exception as error:  # timeout, conexión rechazada, etc.
        return None, url, str(error).encode(), time.perf_counter() - inicio


def usuario_virtual(numero, base, usuario, clave, vueltas, retardo):
    time.sleep(retardo)
    galletas = http.cookiejar.CookieJar()
    abridor = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(galletas))
    login = base + "/seguridad/login/"

    estado, _, html, segundos = pedir(abridor, login)
    registrar("Login (GET)", segundos, None if estado == 200 else f"usuario {numero}: HTTP {estado}")
    token = re.search(rb'name="csrfmiddlewaretoken" value="([^"]+)"', html or b"")
    if not token:
        registrar("Login (POST)", 0, f"usuario {numero}: no se obtuvo el token CSRF")
        return

    estado, destino, _, segundos = pedir(
        abridor, login,
        {"csrfmiddlewaretoken": token.group(1).decode(), "username": usuario, "password": clave},
        referer=login,
    )
    exito = estado == 200 and "/seguridad/login/" not in destino
    registrar("Login (POST)", segundos, None if exito else f"usuario {numero}: no inició sesión (HTTP {estado})")
    if not exito:
        return

    for _ in range(vueltas):
        for nombre, ruta in PANTALLAS:
            estado, destino, _, segundos = pedir(abridor, base + ruta)
            problema = None
            if estado != 200:
                problema = f"usuario {numero}: HTTP {estado}"
            elif "/seguridad/login/" in destino:
                problema = f"usuario {numero}: la sesión se perdió"
            registrar(nombre, segundos, problema)


def percentil(valores, p):
    if not valores:
        return 0.0
    ordenados = sorted(valores)
    indice = min(len(ordenados) - 1, max(0, round(p / 100 * len(ordenados)) - 1))
    return ordenados[indice]


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--url", required=True, help="Dirección base, ej.: http://44.217.180.71")
    parser.add_argument("--usuarios", type=int, default=50, help="Usuarios simultáneos (por defecto 50).")
    parser.add_argument("--vueltas", type=int, default=5, help="Recorridos completos por usuario.")
    parser.add_argument("--rampa", type=float, default=5.0, help="Segundos en que se van sumando los usuarios.")
    parser.add_argument("--salida", help="Archivo .json donde guardar el resultado.")
    args = parser.parse_args()

    # La consola de Windows no siempre acepta UTF-8: se reemplaza lo que
    # no pueda mostrar en vez de fallar.
    for flujo in (sys.stdout, sys.stderr):
        if hasattr(flujo, "reconfigure"):
            flujo.reconfigure(errors="replace")

    usuario = os.environ.get("SGR_ESTRES_USUARIO")
    clave = os.environ.get("SGR_ESTRES_CLAVE")
    if not usuario or not clave:
        sys.exit("Defina SGR_ESTRES_USUARIO y SGR_ESTRES_CLAVE con una cuenta de prueba.")

    base = args.url.rstrip("/")
    print(f"Prueba de estrés: {args.usuarios} usuarios, {args.vueltas} vueltas, rampa {args.rampa}s -> {base}")

    inicio = time.perf_counter()
    with ThreadPoolExecutor(max_workers=args.usuarios) as grupo:
        for n in range(args.usuarios):
            retardo = args.rampa * n / max(args.usuarios, 1)
            grupo.submit(usuario_virtual, n + 1, base, usuario, clave, args.vueltas, retardo)
    duracion = time.perf_counter() - inicio

    total = sum(len(v) for v in resultados.values())
    total_errores = sum(len(v) for v in errores.values())
    todos = [s for v in resultados.values() for s in v]
    p95_global = percentil(todos, 95)

    print(f"\n{'Pantalla':<22}{'Solic.':>7}{'Errores':>8}{'Mediana':>9}{'p90':>8}{'p95':>8}{'Máx':>8}")
    filas = []
    for nombre in ["Login (GET)", "Login (POST)"] + [p for p, _ in PANTALLAS]:
        tiempos = resultados.get(nombre, [])
        fila = {
            "pantalla": nombre,
            "solicitudes": len(tiempos),
            "errores": len(errores.get(nombre, [])),
            "mediana": statistics.median(tiempos) if tiempos else 0.0,
            "p90": percentil(tiempos, 90),
            "p95": percentil(tiempos, 95),
            "maximo": max(tiempos) if tiempos else 0.0,
        }
        filas.append(fila)
        print(f"{nombre:<22}{fila['solicitudes']:>7}{fila['errores']:>8}"
              f"{fila['mediana']:>8.2f}s{fila['p90']:>7.2f}s{fila['p95']:>7.2f}s{fila['maximo']:>7.2f}s")

    tasa_error = total_errores / total * 100 if total else 100.0
    aprobada = total_errores == 0 and p95_global <= UMBRAL_P95
    print(f"\nTotal: {total} solicitudes en {duracion:.1f}s ({total / duracion:.1f} solicitudes/s)")
    print(f"Errores: {total_errores} ({tasa_error:.2f} %) · p95 global: {p95_global:.2f}s (umbral {UMBRAL_P95}s)")
    print("RESULTADO: " + ("APROBADA" if aprobada else "NO APROBADA"))

    for nombre, lista in errores.items():
        for detalle in lista[:3]:
            print(f"  · {nombre}: {detalle}")

    if args.salida:
        with open(args.salida, "w", encoding="utf-8") as archivo:
            json.dump({
                "url": base, "usuarios": args.usuarios, "vueltas": args.vueltas,
                "duracion_s": round(duracion, 2), "solicitudes": total,
                "solicitudes_por_segundo": round(total / duracion, 2),
                "errores": total_errores, "p95_global_s": round(p95_global, 3),
                "aprobada": aprobada, "pantallas": filas,
                "fecha": time.strftime("%Y-%m-%d %H:%M:%S"),
            }, archivo, ensure_ascii=False, indent=2)
        print(f"Resultado guardado en {args.salida}")

    sys.exit(0 if aprobada else 1)


if __name__ == "__main__":
    main()
