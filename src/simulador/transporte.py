"""Como as leituras saem do simulador.

Hoje só existe o modo arquivo (NDJSON, uma leitura por linha), porque o
gateway em Go da próxima fase ainda não existe. O contrato de saída já é
o que o gateway vai consumir depois: um objeto JSON por leitura, um
sensor por linha, para virar uma linha de goroutine no lado do Go sem
precisar mudar nada aqui.
"""

from __future__ import annotations

import dataclasses
import json
import sys
from typing import IO, Iterable

from .sensor import LeituraSensor


def leitura_para_json(leitura: LeituraSensor) -> str:
    return json.dumps(dataclasses.asdict(leitura), ensure_ascii=False)


def escrever_ndjson(leituras: Iterable[LeituraSensor], destino: IO[str] = sys.stdout) -> None:
    for leitura in leituras:
        destino.write(leitura_para_json(leitura) + "\n")
    destino.flush()
