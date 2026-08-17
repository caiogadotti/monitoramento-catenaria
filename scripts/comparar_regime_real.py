"""Compara o regime acelerado da demo contra os números reais publicados.

Roda o mesmo modelo físico (Basquin/Miner) duas vezes: uma com
EXPOENTE_BASQUIN/TENSAO_REFERENCIA_N (os valores acelerados que o resto
do projeto usa por padrão) e outra com EXPOENTE_BASQUIN_REAL/
TENSAO_REFERENCIA_REAL_N (os valores citados de fontes públicas, ver
docstring de src/simulador/sensor.py). Mede quantas passagens de trem
cada regime precisa para cruzar o limiar crítico.

Isso não muda nada no pipeline em uso, é só para responder de forma
concreta "quanto o regime da demo está acelerado em relação ao real".

Uso:
    python scripts/comparar_regime_real.py
"""

import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from src.simulador.sensor import (
    EXPOENTE_BASQUIN,
    EXPOENTE_BASQUIN_REAL,
    LIMIAR_CRITICO,
    TENSAO_REFERENCIA_N,
    TENSAO_REFERENCIA_REAL_N,
    PontoSensor,
)

TRENS_POR_DIA = 120  # ordem de grandeza de uma linha intercidades de médio tráfego


def passagens_ate_critico(tensao_referencia_n, expoente_basquin, tensao_base_n, seed, limite_passagens=2_000_000):
    rng = np.random.default_rng(seed)
    ponto = PontoSensor(sensor_id="CMP", km=0.0, tensao_base_n=tensao_base_n, _rng=rng)
    for i in range(1, limite_passagens + 1):
        amplitude = rng.uniform(3000, 9000)
        ponto.registrar_passagem_de_trem(amplitude, tensao_referencia_n, expoente_basquin)
        if ponto.dano_acumulado >= LIMIAR_CRITICO:
            return i
    return None


def main():
    tensao_base_n = 13000.0
    seed = 42

    passagens_demo = passagens_ate_critico(TENSAO_REFERENCIA_N, EXPOENTE_BASQUIN, tensao_base_n, seed)
    passagens_real = passagens_ate_critico(TENSAO_REFERENCIA_REAL_N, EXPOENTE_BASQUIN_REAL, tensao_base_n, seed)

    print("=== Regime acelerado da demo ===")
    print(f"TENSAO_REFERENCIA_N = {TENSAO_REFERENCIA_N:.0f} N, EXPOENTE_BASQUIN = {EXPOENTE_BASQUIN}")
    print(f"Passagens até o limiar crítico: {passagens_demo}")
    if passagens_demo:
        print(f"Em {TRENS_POR_DIA} trens/dia: {passagens_demo / TRENS_POR_DIA:.1f} dias")

    print("\n=== Regime real (citado, ver docstring de sensor.py) ===")
    print(f"TENSAO_REFERENCIA_REAL_N = {TENSAO_REFERENCIA_REAL_N:.0f} N, EXPOENTE_BASQUIN_REAL = {EXPOENTE_BASQUIN_REAL}")
    if passagens_real is None:
        print(f"Passagens até o limiar crítico: mais de {2_000_000:,}".replace(",", "."))
        print(f"Em {TRENS_POR_DIA} trens/dia: mais de {2_000_000 / TRENS_POR_DIA / 365:.0f} anos")
    else:
        print(f"Passagens até o limiar crítico: {passagens_real}")
        print(f"Em {TRENS_POR_DIA} trens/dia: {passagens_real / TRENS_POR_DIA:.1f} dias "
              f"({passagens_real / TRENS_POR_DIA / 365:.2f} anos)")

    if passagens_demo and passagens_real:
        print(f"\nFator de aceleracao: {passagens_real / passagens_demo:.0f}x")


if __name__ == "__main__":
    main()
