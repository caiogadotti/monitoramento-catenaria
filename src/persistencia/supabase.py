"""Persistência das leituras e alertas no Postgres do Supabase.

Duas tabelas, criadas via migration no projeto Supabase (não neste
código): `catenaria_leituras` (uma linha por leitura processada, com as
duas estimativas de dano, SNR e RUL) e `catenaria_alertas` (uma linha por
transição de estado para ATENCAO ou CRITICO).

Nenhuma credencial fica no código. A conexão vem inteira da variável de
ambiente `SUPABASE_DB_URL` (string `postgresql://usuario:senha@host:porta/banco`,
o formato que o pooler de sessão do Supabase expõe direto no painel do
projeto). Sem essa variável, o script falha cedo com uma mensagem clara
em vez de tentar adivinhar ou usar um valor padrão.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Iterator

import psycopg2
import psycopg2.extras


def _url_conexao() -> str:
    url = os.environ.get("SUPABASE_DB_URL")
    if not url:
        raise RuntimeError(
            "variável de ambiente SUPABASE_DB_URL não definida. "
            "Copie .env.example para .env, preencha a connection string do "
            "pooler (Project Settings > Database, no painel do Supabase) e "
            "exporte antes de rodar com --supabase."
        )
    return url


def abrir_conexao() -> psycopg2.extensions.connection:
    return psycopg2.connect(_url_conexao())


@contextmanager
def conectar() -> Iterator[psycopg2.extensions.connection]:
    conexao = abrir_conexao()
    try:
        yield conexao
    finally:
        conexao.close()


def gravar_leituras_lote(conexao, linhas: list[tuple]) -> None:
    """Insere um lote de leituras. Cada tupla segue a ordem das colunas da tabela."""
    if not linhas:
        return
    with conexao.cursor() as cursor:
        psycopg2.extras.execute_values(
            cursor,
            """
            insert into catenaria_leituras
                (sensor_id, km, lido_em, tensao_mecanica_n, temperatura_c,
                 dano_ciclos, dano_espectral, snr_db, rul_segundos, estado,
                 ciclos_contados, dano_espectral_bruto, desgaste_acelerado, dano_ml)
            values %s
            """,
            linhas,
        )
    conexao.commit()


def gravar_alerta(conexao, sensor_id: str, km: float, estado: str, dano_ciclos: float, dano_espectral: float) -> None:
    with conexao.cursor() as cursor:
        cursor.execute(
            """
            insert into catenaria_alertas (sensor_id, km, estado, dano_ciclos, dano_espectral)
            values (%s, %s, %s, %s, %s)
            """,
            (sensor_id, km, estado, dano_ciclos, dano_espectral),
        )
    conexao.commit()
