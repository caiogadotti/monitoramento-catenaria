"""Calibra a relação entre piso de ruído espectral e dano acumulado.

Duas versões, dois erros diferentes:

1. A primeira tentativa derivava a relação analiticamente via aproximação
   de Parseval e errava por uma constante grande (dano real 1.0 virava
   estimativa de 0.018).
2. A segunda calibrava empiricamente, mas ajustava uma RETA entre piso de
   potência e dano. Fisicamente errado: potência é o quadrado do desvio
   padrão do ruído, e é o desvio padrão que cresce linear com o dano
   (`RUIDO_BASE + RUIDO_POR_DANO * dano`, a mesma fórmula que
   `src/simulador/sensor.py` usa para gerar o sinal). Ajustar uma reta
   numa relação quadrática funciona mal perto de dano=0 (a reta
   extrapolava para potência negativa ali) e sistematicamente mal em
   qualquer faixa de tensão/temperatura fora da usada no ajuste: erro
   médio de 0.128 rodando o pipeline completo, contra 0.06 medido no
   ajuste isolado.

Este script ajusta a forma certa: um único fator de escala `k` tal que
`piso_de_potencia ≈ k * intensidade_ruido²`, onde `intensidade_ruido` já é
conhecida (é a mesma fórmula do simulador). k deveria ficar perto de 1.0
se a hipótese física estiver certa (potência por bin do ruído branco ≈
variância do processo), e a validação abaixo confirma isso.

Uso:
    python scripts/calibrar_espectro.py
"""

import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from src.simulador.sensor import PontoSensor
from src.analise.espectro import LARGURA_EXCLUSAO_HZ, RUIDO_BASE, RUIDO_POR_DANO, _piso_de_potencia

AMOSTRAS_POR_NIVEL = 30


def coletar(niveis_de_dano, seed):
    """Varia tensão de base e temperatura junto com o dano, como a rede real faz.

    A primeira versão deste script fixava tensão de base em 13000N e
    temperatura em 25°C, só variando o dano. Isso escondia o erro do
    modelo linear: calibrado e validado nas mesmas condições
    artificialmente estreitas, parecia funcionar bem, e só quebrou
    rodando no pipeline de verdade, onde tensão de base varia por sensor
    (12000-14000N) e temperatura varia ao longo do dia simulado.
    """
    rng = np.random.default_rng(seed)
    danos, pisos = [], []
    for dano in niveis_de_dano:
        for _ in range(AMOSTRAS_POR_NIVEL):
            tensao_base = rng.uniform(12000, 14000)
            temperatura = rng.uniform(16, 32)
            ponto = PontoSensor(sensor_id="CAL", km=0.0, tensao_base_n=tensao_base, _rng=rng)
            ponto._dano_acumulado = dano
            leitura = ponto.ler(timestamp=0, passagem_de_trem=False, temperatura_c=temperatura)
            danos.append(dano)
            pisos.append(_piso_de_potencia(leitura.vibracao))
    return np.array(danos), np.array(pisos)


def ajustar_k(danos, pisos):
    intensidade_prevista = RUIDO_BASE + RUIDO_POR_DANO * danos
    return np.sum(pisos * intensidade_prevista**2) / np.sum(intensidade_prevista**4)


def estimar_dano(pisos, k):
    intensidade_estimada = np.sqrt(np.clip(pisos / k, 0, None))
    return np.clip((intensidade_estimada - RUIDO_BASE) / RUIDO_POR_DANO, 0, 1)


def main():
    ajuste = np.linspace(0, 1, 11)
    reserva = np.linspace(0.05, 0.95, 10)  # niveis diferentes dos usados no ajuste

    danos_ajuste, pisos_ajuste = coletar(ajuste, seed=42)
    k = ajustar_k(danos_ajuste, pisos_ajuste)

    print(f"piso_de_potencia = {k:.6f} * (RUIDO_BASE + RUIDO_POR_DANO * dano)^2")
    print(f"k = {k:.6f}  (perto de 1.0 confirma a hipotese fisica: potencia por bin ~ variancia)")

    danos_reserva, pisos_reserva = coletar(reserva, seed=7)  # semente diferente do ajuste
    estimados = estimar_dano(pisos_reserva, k)
    erro = np.mean(np.abs(danos_reserva - estimados))
    correlacao = np.corrcoef(danos_reserva, estimados)[0, 1]

    print(f"\nvalidacao em niveis de dano reservados, com tensao de base e")
    print(f"temperatura variando (nao so o dano, como a rede real faz):")
    print(f"  erro medio absoluto: {erro:.4f}")
    print(f"  correlacao estimado vs real: {correlacao:.4f}")
    print(f"\nlargura de exclusao dos picos conhecidos: {LARGURA_EXCLUSAO_HZ} Hz")
    print(f"\nCole o valor de k calibrado em src/analise/espectro.py")


if __name__ == "__main__":
    main()
