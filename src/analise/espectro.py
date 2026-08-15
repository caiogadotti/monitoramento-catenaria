"""Estima o desgaste a partir do piso de ruído espectral da vibração.

O sinal de vibração (ver `src.simulador.sensor._sintetizar_vibracao`) soma
três componentes: uma oscilação estrutural marcada na frequência de
ressonância do cabo, o acoplamento de 60Hz da rede de tração, e ruído de
banda larga cuja intensidade (desvio padrão) cresce linear com o dano
acumulado: `intensidade_ruido = RUIDO_BASE + RUIDO_POR_DANO * dano`.

Este módulo faz o que um sensor real exigiria: separar os dois picos
conhecidos do resto do espectro via FFT, e usar a energia que sobra (o
piso de ruído) como indício independente de desgaste. Nunca lê o
`dano_acumulado` que o simulador já sabe.
"""

from __future__ import annotations

import numpy as np

from src.simulador.sensor import FREQUENCIA_ESTRUTURAL_HZ, FREQUENCIA_REDE_HZ, TAXA_AMOSTRAGEM_HZ

LARGURA_EXCLUSAO_HZ = 3.0

RUIDO_BASE = 0.05
RUIDO_POR_DANO = 0.6

# piso_de_potencia ≈ K_POTENCIA * intensidade_ruido²
#
# Potência é o quadrado de uma amplitude, então o piso de ruído no
# espectro cresce com o QUADRADO do desvio padrão do ruído, não linear
# nele. A primeira versão deste módulo ajustava uma reta entre piso e
# dano diretamente, o que funcionava bem calibrado e validado nas mesmas
# condições estreitas (tensão de base fixa, temperatura fixa), mas errava
# por mais de 2x (0.128 de erro médio) rodando no pipeline completo, com
# tensão de base e temperatura variando por sensor como a rede real faz.
#
# K_POTENCIA medido por scripts/calibrar_espectro.py, com tensão de base
# e temperatura variando junto com o dano no dado de calibração. Fica
# perto de 1.0 porque, fisicamente, a potência média por bin de ruído
# branco é aproximadamente igual à variância do processo no tempo -- não
# é um número mágico ajustado, é a confirmação de que o modelo físico
# certo (quadrático) bate com o que a FFT mede.
K_POTENCIA = 1.012729


def _separar_espectro(vibracao: list[float]) -> tuple[np.ndarray, np.ndarray]:
    """Retorna (potência dos bins de pico conhecidos, potência dos bins de ruído)."""
    sinal = np.asarray(vibracao, dtype=float)
    n = len(sinal)
    if n < 8:
        return np.array([]), np.array([])

    espectro_potencia = (np.abs(np.fft.rfft(sinal)) ** 2) / n
    frequencias = np.fft.rfftfreq(n, d=1.0 / TAXA_AMOSTRAGEM_HZ)

    excluidos = np.zeros_like(frequencias, dtype=bool)
    for pico_hz in (FREQUENCIA_ESTRUTURAL_HZ, FREQUENCIA_REDE_HZ):
        excluidos |= np.abs(frequencias - pico_hz) <= LARGURA_EXCLUSAO_HZ

    return espectro_potencia[excluidos], espectro_potencia[~excluidos]


def _piso_de_potencia(vibracao: list[float]) -> float:
    """Potência média do espectro fora dos dois picos conhecidos (18Hz, 60Hz)."""
    _, bins_de_ruido = _separar_espectro(vibracao)
    return float(bins_de_ruido.mean()) if bins_de_ruido.size else 0.0


def estimar_dano_espectral(vibracao: list[float]) -> float:
    piso = _piso_de_potencia(vibracao)
    intensidade_estimada = (max(piso, 0.0) / K_POTENCIA) ** 0.5
    dano_estimado = (intensidade_estimada - RUIDO_BASE) / RUIDO_POR_DANO
    return float(np.clip(dano_estimado, 0.0, 1.0))


def estimar_snr_db(vibracao: list[float]) -> float:
    """Relação sinal-ruído em dB: potência dos picos conhecidos sobre o piso de ruído.

    Uma via eletrificada tem interferência eletromagnética alta, e o motor
    já separa picos de ruído para estimar dano; o SNR é a mesma separação
    lida do outro lado, e serve como indicador independente da qualidade
    do sinal antes de confiar no resto da análise.
    """
    bins_de_pico, bins_de_ruido = _separar_espectro(vibracao)
    if bins_de_pico.size == 0 or bins_de_ruido.size == 0:
        return 0.0

    potencia_sinal = float(bins_de_pico.mean())
    potencia_ruido = float(bins_de_ruido.mean())
    if potencia_ruido <= 0.0:
        return float("inf")

    return float(10.0 * np.log10(potencia_sinal / potencia_ruido))
