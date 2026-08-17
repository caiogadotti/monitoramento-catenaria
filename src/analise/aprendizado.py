"""Estimador de dano por aprendizado de máquina, para comparação honesta.

Motivação: a literatura real de monitoramento de catenária (ver
"Referências" no README) resolve estimar desgaste a partir de vibração
com redes neurais treinadas em dado real de operação. Não dá para
comparar essa rede com o motor deste projeto de forma justa, o dataset de
treino delas é proprietário e não público, e o "verdadeiro" de cada uma é
diferente (aceleração real do pantógrafo vs. vibração sintética deste
simulador).

O que dá para fazer, e que este módulo faz: treinar uma rede neural
pequena usando o **mesmo simulador e a mesma verdade** que já usamos para
medir o erro dos outros dois estimadores (`fadiga.py`, `espectro.py`).
Assim os três competem na régua, sem misturar domínios.

Ao contrário do estimador espectral, que usa uma feature já calculada à
mão (o piso de ruído fora dos picos conhecidos), este recebe o espectro
de potência bruto inteiro e aprende sozinho o que importa, mais perto do
que uma rede treinada em dado real faria.
"""

from __future__ import annotations

import numpy as np

from src.simulador.sensor import TAXA_AMOSTRAGEM_HZ, TENSAO_REFERENCIA_N

TEMPERATURA_REFERENCIA_C = 40.0


def extrair_atributos(vibracao: list[float], tensao_mecanica_n: float, temperatura_c: float) -> np.ndarray:
    """Espectro de potência bruto (todos os bins) + tensão e temperatura normalizadas.

    Nenhum conhecimento de onde ficam os picos de 18Hz/60Hz entra aqui,
    ao contrário de `espectro.py`. A rede tem que descobrir sozinha quais
    bins carregam sinal útil.
    """
    sinal = np.asarray(vibracao, dtype=float)
    espectro_potencia = (np.abs(np.fft.rfft(sinal)) ** 2) / len(sinal)
    return np.concatenate([
        espectro_potencia,
        [tensao_mecanica_n / TENSAO_REFERENCIA_N, temperatura_c / TEMPERATURA_REFERENCIA_C],
    ])
