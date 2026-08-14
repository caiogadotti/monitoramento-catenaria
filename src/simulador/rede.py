"""Rede de pontos de sensor distribuídos ao longo de um trecho ferroviário.

Isolado de `sensor.py` (o modelo físico de um ponto) para poder trocar a
distribuição espacial ou a política de trens sem tocar na física de cada
sensor individual.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import numpy as np

from .sensor import LeituraSensor, PontoSensor

TEMPERATURA_MEDIA_C = 24.0
AMPLITUDE_TERMICA_DIARIA_C = 8.0
PERIODO_DIA_SIMULADO_S = 300.0  # um "dia" inteiro em 5 minutos, para o ciclo termico aparecer rapido


@dataclass
class ConfiguracaoRede:
    extensao_km: float = 40.0
    sensores_por_km: int = 50
    fracao_pontos_degradados: float = 0.02  # fracao da rede com taxa_desgaste alta, de proposito
    intervalo_trens_s: float = 6.0
    seed: int = 42


class RedeCatenaria:
    """Gera e mantém o estado de todos os pontos de sensor da linha."""

    def __init__(self, config: ConfiguracaoRede | None = None):
        self.config = config or ConfiguracaoRede()
        self._rng = np.random.default_rng(self.config.seed)
        self.pontos = self._criar_pontos()
        self._inicio = time.time()
        self._proxima_passagem = self._inicio + self.config.intervalo_trens_s

    def _criar_pontos(self) -> list[PontoSensor]:
        total = int(self.config.extensao_km * self.config.sensores_por_km)
        posicoes = np.linspace(0, self.config.extensao_km, total)

        indices_degradados = self._rng.choice(
            total, size=max(1, int(total * self.config.fracao_pontos_degradados)), replace=False
        )

        pontos = []
        for i, km in enumerate(posicoes):
            degradado = i in indices_degradados
            taxa = self._rng.uniform(8.0, 20.0) if degradado else self._rng.uniform(0.5, 1.5)
            pontos.append(
                PontoSensor(
                    sensor_id=f"CAT-{i:05d}",
                    km=round(float(km), 3),
                    taxa_desgaste=taxa,
                    tensao_base_n=self._rng.uniform(12000, 14000),
                )
            )
        return pontos

    def _temperatura_atual(self, agora: float) -> float:
        fase = ((agora - self._inicio) % PERIODO_DIA_SIMULADO_S) / PERIODO_DIA_SIMULADO_S
        return TEMPERATURA_MEDIA_C + AMPLITUDE_TERMICA_DIARIA_C * np.sin(2 * np.pi * fase)

    def _passagem_de_trem_agora(self, agora: float) -> bool:
        if agora < self._proxima_passagem:
            return False
        self._proxima_passagem = agora + self.config.intervalo_trens_s
        return True

    def ler_janela(self) -> list[LeituraSensor]:
        """Uma leitura de todos os pontos da rede no instante atual."""
        agora = time.time()
        temperatura = self._temperatura_atual(agora)
        passagem = self._passagem_de_trem_agora(agora)
        return [ponto.ler(agora, passagem, temperatura) for ponto in self.pontos]

    def resumo_estado(self) -> dict[str, int]:
        contagem = {"NORMAL": 0, "ATENCAO": 0, "CRITICO": 0}
        for ponto in self.pontos:
            contagem[ponto.estado] += 1
        return contagem
