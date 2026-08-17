"""Escolhe o tamanho da média móvel do estimador espectral por medição.

A estimativa espectral isolada mede o ruído de uma janela de 1 segundo e
carrega a variância desse ruído. Sensores com dano perto do limiar de
alerta cruzavam a fronteira para cima e para baixo a cada leitura,
gerando alerta repetido para o mesmo ponto (num teste, um sensor
oscilou 3 vezes em 19 leituras).

Suavizar resolve a oscilação, mas cobra atraso: quanto maior a janela,
mais leituras a média demora para refletir uma degradação nova. Este
script mede os dois lados em vez de escolher o número no chute:

- erro médio absoluto contra o dano real do simulador
- mudanças de estado por sensor (proxy direto da oscilação)
- atraso até o primeiro alerta, em leituras, nos sensores defeituosos

Uso:
    python scripts/simular_sensores.py --extensao-km 6 --sensores-por-km 25 \
        --duracao-s 20 > dados.ndjson
    python scripts/calibrar_suavizacao.py dados.ndjson
"""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from src.analise.motor import MotorAnalise

TAMANHOS = [1, 2, 3, 5, 8, 12]


def avaliar(leituras: list[dict], janelas: int) -> dict:
    motor = MotorAnalise(janelas_suavizacao=janelas)
    erros: list[float] = []
    estados: dict[str, list[str]] = {}
    primeiro_alerta: dict[str, int] = {}
    indice_por_sensor: dict[str, int] = {}

    for leitura in leituras:
        avaliacao = motor.processar_leitura(leitura)
        sensor = avaliacao.sensor_id

        i = indice_por_sensor.get(sensor, 0)
        indice_por_sensor[sensor] = i + 1

        erros.append(abs(avaliacao.dano - leitura["dano_acumulado"]))
        estados.setdefault(sensor, []).append(avaliacao.estado)

        if avaliacao.estado != "NORMAL" and sensor not in primeiro_alerta:
            primeiro_alerta[sensor] = i

    mudancas = sum(
        1
        for historico in estados.values()
        for a, b in zip(historico, historico[1:])
        if a != b
    )
    # oscilação = mudanças além da primeira transição legítima de cada sensor
    sensores_que_alertaram = len(primeiro_alerta)
    oscilacoes = max(0, mudancas - sensores_que_alertaram)

    return {
        "erro": sum(erros) / len(erros),
        "mudancas": mudancas,
        "oscilacoes": oscilacoes,
        "alertaram": sensores_que_alertaram,
        "atraso": (
            sum(primeiro_alerta.values()) / len(primeiro_alerta) if primeiro_alerta else float("nan")
        ),
    }


def main() -> None:
    caminho = sys.argv[1]
    with open(caminho, encoding="utf-8") as f:
        leituras = [json.loads(l) for l in f if l.strip()]

    print(f"{len(leituras)} leituras, {len({l['sensor_id'] for l in leituras})} sensores\n")
    print("janelas | erro medio | sensores alertados | oscilacoes | atraso ate 1o alerta")
    print("--------|------------|--------------------|------------|---------------------")
    for n in TAMANHOS:
        r = avaliar(leituras, n)
        print(
            f"{n:7d} | {r['erro']:10.4f} | {r['alertaram']:18d} | "
            f"{r['oscilacoes']:10d} | {r['atraso']:19.1f}"
        )

    print("\nescolher o menor tamanho que zera a oscilacao sem perder sensor")
    print("alertado nem inflar o atraso; colar o valor em JANELAS_SUAVIZACAO")
    print("de src/analise/espectro.py")


if __name__ == "__main__":
    main()
