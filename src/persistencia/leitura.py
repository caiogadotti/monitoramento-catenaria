"""Leitura das tabelas do Supabase via REST (PostgREST), só select.

O dashboard não precisa da connection string do Postgres, só da chave
anon: as duas tabelas (`catenaria_leituras`, `catenaria_alertas`) têm RLS
habilitada com uma policy de `select` pública pra `anon`/`authenticated`
e nenhuma policy de escrita, então a chave anon nunca consegue gravar ou
apagar nada, mesmo exposta no cliente. É por isso que o motor de análise
usa a connection string do Postgres (`supabase.py`) e o dashboard usa a
API REST com a chave anon: dois níveis de acesso para duas necessidades
diferentes.
"""

from __future__ import annotations

import requests

TIMEOUT_S = 10


def _cabecalhos(chave_anon: str) -> dict:
    return {
        "apikey": chave_anon,
        "Authorization": f"Bearer {chave_anon}",
    }


# O PostgREST do Supabase corta a resposta em 1000 linhas por requisição,
# independente do `limit` que se peça, então buscar mais exige paginar com
# o cabeçalho Range. Sem isso o painel recebia só as 1000 leituras mais
# recentes e mostrava esse número como se fosse o total.
PAGINA = 1000


def buscar_leituras(url_projeto: str, chave_anon: str, limite: int = 5000) -> list[dict]:
    coletadas: list[dict] = []

    while len(coletadas) < limite:
        inicio = len(coletadas)
        fim = min(inicio + PAGINA, limite) - 1

        resposta = requests.get(
            f"{url_projeto}/rest/v1/catenaria_leituras",
            headers={**_cabecalhos(chave_anon), "Range-Unit": "items", "Range": f"{inicio}-{fim}"},
            params={"order": "lido_em.desc"},
            timeout=TIMEOUT_S,
        )
        resposta.raise_for_status()

        pagina = resposta.json()
        coletadas.extend(pagina)
        if len(pagina) < fim - inicio + 1:
            break

    return coletadas


def buscar_alertas(url_projeto: str, chave_anon: str, limite: int = 100) -> list[dict]:
    resposta = requests.get(
        f"{url_projeto}/rest/v1/catenaria_alertas",
        headers=_cabecalhos(chave_anon),
        params={"order": "disparado_em.desc", "limit": str(limite)},
        timeout=TIMEOUT_S,
    )
    resposta.raise_for_status()
    return resposta.json()
