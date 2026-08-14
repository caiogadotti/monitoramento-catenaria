"""Como as leituras saem do simulador.

O contrato é o mesmo em qualquer destino: um objeto JSON por leitura, um
sensor por linha (NDJSON). `escrever_ndjson` aceita qualquer `IO[str]`, por
isso o mesmo código atende três casos sem duplicação: escrever em stdout
para inspeção manual, redirecionar para um arquivo, ou escrever direto
numa conexão TCP com o gateway em Go (via `conectar_gateway`, que devolve
um socket empacotado como arquivo de texto).
"""

from __future__ import annotations

import dataclasses
import json
import socket
import sys
from contextlib import contextmanager
from typing import IO, Iterable, Iterator

from .sensor import LeituraSensor


def leitura_para_json(leitura: LeituraSensor) -> str:
    return json.dumps(dataclasses.asdict(leitura), ensure_ascii=False)


def escrever_ndjson(leituras: Iterable[LeituraSensor], destino: IO[str] = sys.stdout) -> None:
    for leitura in leituras:
        destino.write(leitura_para_json(leitura) + "\n")
    destino.flush()


@contextmanager
def conectar_gateway(endereco: str) -> Iterator[IO[str]]:
    """Abre uma conexão TCP com o gateway e devolve como arquivo de texto.

    `endereco` no formato "host:porta". Usa IPv4 explícito por padrão nas
    chamadas (ver README, seção do gateway, sobre por que "localhost" no
    Windows resolve para IPv6 primeiro e pode ser recusado por um listener
    que só aceita IPv4).
    """
    host, porta = endereco.rsplit(":", 1)
    with socket.create_connection((host, int(porta))) as conexao:
        arquivo = conexao.makefile("w", encoding="utf-8", newline="\n")
        try:
            yield arquivo
        finally:
            arquivo.flush()
