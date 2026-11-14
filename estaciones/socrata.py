"""Cliente mínimo para la API Socrata (SODA) de www.datos.gov.co.

Reutilizable por cualquier conector cuyos datos estén publicados en datos.gov.co.
Si existe la variable de entorno SOCRATA_APP_TOKEN se envía como token de
aplicación (opcional; reduce el riesgo de que la API limite las peticiones).
"""

from __future__ import annotations

import os
import time

import requests

DOMINIO = "https://www.datos.gov.co"


class ErrorSocrata(RuntimeError):
    pass


class ClienteSocrata:
    def __init__(self, dominio: str = DOMINIO, timeout_s: float = 120, reintentos: int = 3):
        self.dominio = dominio.rstrip("/")
        self.timeout_s = timeout_s
        self.reintentos = reintentos
        self.sesion = requests.Session()
        self.sesion.headers["User-Agent"] = "hidrologia-estaciones/0.1 (python-requests)"
        token = os.environ.get("SOCRATA_APP_TOKEN")
        if token:
            self.sesion.headers["X-App-Token"] = token

    def consultar(self, dataset: str, params: dict, timeout_s: float | None = None) -> list[dict]:
        """GET /resource/<dataset>.json con parámetros SoQL. Reintenta errores transitorios.

        Los timeouts se propagan como `requests.Timeout` sin reintentar, para que quien
        llama pueda partir la consulta en trozos más pequeños.
        """
        url = f"{self.dominio}/resource/{dataset}.json"
        ultimo_error: Exception | None = None
        for intento in range(1, self.reintentos + 1):
            try:
                r = self.sesion.get(url, params=params, timeout=(15, timeout_s or self.timeout_s))
            except requests.Timeout:
                raise
            except requests.RequestException as e:  # error de red: reintentar
                ultimo_error = e
            else:
                if r.status_code == 200:
                    return r.json()
                if r.status_code in (429, 500, 502, 503, 504):
                    ultimo_error = ErrorSocrata(f"HTTP {r.status_code}: {r.text[:200]}")
                else:
                    raise ErrorSocrata(f"HTTP {r.status_code} en {dataset}: {r.text[:300]}")
            time.sleep(2 * intento)
        raise ErrorSocrata(f"Falló la consulta a {dataset} tras {self.reintentos} intentos: {ultimo_error}")
