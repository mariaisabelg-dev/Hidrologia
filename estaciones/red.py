"""Cliente HTTP/JSON genérico con reintentos, para APIs REST de las fuentes regionales."""

from __future__ import annotations

import time

import requests

USER_AGENT = "hidrologia-estaciones/0.1 (python-requests)"


class ErrorFuente(RuntimeError):
    pass


class ClienteJSON:
    def __init__(self, timeout_s: float = 60, reintentos: int = 3, pausa_s: float = 0.0):
        """pausa_s: espera mínima entre peticiones, para no sobrecargar servidores pequeños."""
        self.timeout_s = timeout_s
        self.reintentos = reintentos
        self.pausa_s = pausa_s
        self.sesion = requests.Session()
        self.sesion.headers["User-Agent"] = USER_AGENT

    def get(self, url: str, params: dict | None = None, timeout_s: float | None = None):
        ultimo: Exception | None = None
        for intento in range(1, self.reintentos + 1):
            if self.pausa_s:
                time.sleep(self.pausa_s)
            try:
                r = self.sesion.get(url, params=params, timeout=(15, timeout_s or self.timeout_s))
            except requests.RequestException as e:
                ultimo = e
            else:
                if r.status_code == 200:
                    return r.json()
                if r.status_code in (429, 500, 502, 503, 504):
                    ultimo = ErrorFuente(f"HTTP {r.status_code}")
                else:
                    raise ErrorFuente(f"HTTP {r.status_code} en {url}: {r.text[:200]}")
            time.sleep(2 * intento)
        raise ErrorFuente(f"Falló {url} tras {self.reintentos} intentos: {ultimo}")
