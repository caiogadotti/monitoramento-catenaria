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

from src.analise.aprendizado import coletar_dataset_sintetico, _rede_treinada
from src.analise.espectro import estimar_dano_espectral


def main():
    try:
        import sklearn  # noqa: F401
    except ImportError:
        print("Precisa de scikit-learn: pip install scikit-learn")
        raise SystemExit(1)

    reserva = np.linspace(0.03, 0.97, 12)  # níveis diferentes dos usados no treino da rede

    rede = _rede_treinada()  # treina com a mesma semente/config usada em produção
    X_reserva, y_reserva, vibracoes_reserva = coletar_dataset_sintetico(reserva, seed=7)

    estimados_ml = np.clip(rede.predict(X_reserva), 0.0, 1.0)
    erro_ml = float(np.mean(np.abs(estimados_ml - y_reserva)))
    correlacao_ml = float(np.corrcoef(estimados_ml, y_reserva)[0, 1])

    estimados_espectral = np.array([estimar_dano_espectral(v) for v in vibracoes_reserva])
    erro_espectral = float(np.mean(np.abs(estimados_espectral - y_reserva)))
    correlacao_espectral = float(np.corrcoef(estimados_espectral, y_reserva)[0, 1])

    print(f"{len(y_reserva)} amostras de reserva, mesmo simulador que treinou a rede")
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
