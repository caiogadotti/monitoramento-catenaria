"""Treina um estimador de dano por rede neural e compara com os outros dois.

Gera dados sintéticos com o mesmo simulador usado para calibrar o
estimador espectral (`calibrar_espectro.py`), varia dano, tensão de base
e temperatura juntos, treina uma rede neural pequena
(`sklearn.neural_network.MLPRegressor`) sobre o espectro de potência
bruto, e mede o erro num conjunto reservado nunca visto no treino.

O estimador espectral físico é avaliado no MESMO conjunto reservado, pela
mesma métrica, para a comparação valer alguma coisa. O estimador por
ciclos não entra nessa tabela: ele precisa de uma sequência de leituras
no tempo para estimar a própria linha de base, não dá para avaliar numa
janela isolada como as outras duas.

Uso:
    pip install scikit-learn
    python scripts/treinar_estimador_ml.py
"""

import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from src.simulador.sensor import PontoSensor
from src.analise.espectro import estimar_dano_espectral
from src.analise.aprendizado import extrair_atributos

AMOSTRAS_POR_NIVEL = 40


def coletar(niveis_de_dano, seed):
    rng = np.random.default_rng(seed)
    atributos, danos, vibracoes, tensoes, temperaturas = [], [], [], [], []
    for dano in niveis_de_dano:
        for _ in range(AMOSTRAS_POR_NIVEL):
            tensao_base = rng.uniform(12000, 14000)
            temperatura = rng.uniform(16, 32)
            ponto = PontoSensor(sensor_id="ML", km=0.0, tensao_base_n=tensao_base, _rng=rng)
            ponto._dano_acumulado = dano
            leitura = ponto.ler(timestamp=0, passagem_de_trem=False, temperatura_c=temperatura)
            atributos.append(extrair_atributos(leitura.vibracao, leitura.tensao_mecanica_n, temperatura))
            vibracoes.append(leitura.vibracao)
            tensoes.append(leitura.tensao_mecanica_n)
            temperaturas.append(temperatura)
            danos.append(dano)
    return np.array(atributos), np.array(danos), vibracoes


def main():
    try:
        from sklearn.neural_network import MLPRegressor
    except ImportError:
        print("Precisa de scikit-learn: pip install scikit-learn")
        raise SystemExit(1)

    ajuste = np.linspace(0, 1, 15)
    reserva = np.linspace(0.03, 0.97, 12)  # níveis diferentes dos usados no treino

    X_treino, y_treino, _ = coletar(ajuste, seed=42)
    X_reserva, y_reserva, vibracoes_reserva = coletar(reserva, seed=7)  # semente diferente

    rede = MLPRegressor(
        hidden_layer_sizes=(32, 16),
        activation="relu",
        max_iter=2000,
        random_state=0,
    )
    rede.fit(X_treino, y_treino)

    estimados_ml = np.clip(rede.predict(X_reserva), 0.0, 1.0)
    erro_ml = float(np.mean(np.abs(estimados_ml - y_reserva)))
    correlacao_ml = float(np.corrcoef(estimados_ml, y_reserva)[0, 1])

    estimados_espectral = np.array([estimar_dano_espectral(v) for v in vibracoes_reserva])
    erro_espectral = float(np.mean(np.abs(estimados_espectral - y_reserva)))
    correlacao_espectral = float(np.corrcoef(estimados_espectral, y_reserva)[0, 1])

    print(f"{len(y_treino)} amostras de treino, {len(y_reserva)} de reserva, mesmo simulador")
    print()
    print("Estimador          | erro medio absoluto | correlacao")
    print("-------------------|----------------------|-----------")
    print(f"Rede neural (MLP)  | {erro_ml:20.4f} | {correlacao_ml:.4f}")
    print(f"Espectral (FFT)    | {erro_espectral:20.4f} | {correlacao_espectral:.4f}")
    print()
    print("O estimador por ciclos nao entra aqui: precisa de sequencia no tempo")
    print("para estimar a propria linha de base, nao avalia numa janela isolada.")


if __name__ == "__main__":
    main()
