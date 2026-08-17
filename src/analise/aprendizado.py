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

from functools import lru_cache

import numpy as np

from src.simulador.sensor import TENSAO_REFERENCIA_N

TEMPERATURA_REFERENCIA_C = 40.0
AMOSTRAS_POR_NIVEL_TREINO = 40


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


def coletar_dataset_sintetico(niveis_de_dano, seed):
    """Gera (atributos, dano_real, vibração) variando dano, tensão de base e
    temperatura juntos, como `scripts/calibrar_espectro.py` já fazia.
    """
    from src.simulador.sensor import PontoSensor

    rng = np.random.default_rng(seed)
    atributos, danos, vibracoes = [], [], []
    for dano in niveis_de_dano:
        for _ in range(AMOSTRAS_POR_NIVEL_TREINO):
            tensao_base = rng.uniform(12000, 14000)
            temperatura = rng.uniform(16, 32)
            ponto = PontoSensor(sensor_id="ML", km=0.0, tensao_base_n=tensao_base, _rng=rng)
            ponto._dano_acumulado = dano
            leitura = ponto.ler(timestamp=0, passagem_de_trem=False, temperatura_c=temperatura)
            atributos.append(extrair_atributos(leitura.vibracao, leitura.tensao_mecanica_n, temperatura))
            vibracoes.append(leitura.vibracao)
            danos.append(dano)
    return np.array(atributos), np.array(danos), vibracoes


@lru_cache(maxsize=1)
def _rede_treinada():
    """Treina uma vez por processo e cacheia. Custa ~1s, não vale repetir
    a cada leitura processada nem a cada recarregamento do dashboard.
    """
    from sklearn.neural_network import MLPRegressor

    X, y, _ = coletar_dataset_sintetico(np.linspace(0, 1, 15), seed=42)
    rede = MLPRegressor(hidden_layer_sizes=(32, 16), activation="relu", max_iter=2000, random_state=0)
    rede.fit(X, y)
    return rede


def estimar_dano_ml(vibracao: list[float], tensao_mecanica_n: float, temperatura_c: float) -> float:
    """Estimativa da rede neural para uma leitura real, mesma rede do experimento.

    Se scikit-learn não estiver instalado, devolve NaN em vez de quebrar o
    pipeline principal: este estimador é um complemento comparativo, não
    uma dependência do motor de análise.
    """
    try:
        rede = _rede_treinada()
    except ImportError:
        return float("nan")

    atributos = extrair_atributos(vibracao, tensao_mecanica_n, temperatura_c).reshape(1, -1)
    return float(np.clip(rede.predict(atributos)[0], 0.0, 1.0))
