"""Acumulador de dano por fadiga, independente do simulador.

Reaproveita as constantes do modelo físico (`TENSAO_REFERENCIA_N`,
`EXPOENTE_BASQUIN`, os limiares de estado) de `src.simulador.sensor`
porque são parâmetros de calibração do material, o tipo de número que
vem de uma folha de especificação do cabo, não segredo nenhum.

O que este módulo não reaproveita é o `dano_acumulado` que o simulador já
calculou. Esse campo só existe porque o simulador conhece a física
"verdadeira" por construção. O motor de análise tem que chegar no mesmo
lugar observando só o que um sensor real observaria: a tensão mecânica
lida a cada instante, nada além disso.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.simulador.sensor import (
    EXPOENTE_BASQUIN,
    LIMIAR_ATENCAO,
    LIMIAR_CRITICO,
    TENSAO_REFERENCIA_N,
)

# o quanto a tensão precisa subir acima da linha de base para contar como
# um ciclo de passagem, e não ruído de leitura em torno do repouso
LIMIAR_CICLO_N = 1500.0

# velocidade com que a linha de base acompanha deriva térmica lenta, sem
# se deixar puxar por um ciclo de passagem isolado
GANHO_LINHA_DE_BASE = 0.05


@dataclass
class AcumuladorDano:
    """Replica a regra de Basquin + Palmgren-Miner a partir de leituras cruas.

    Não conhece a tensão de repouso do cabo de antemão (nenhum sensor real
    conheceria), então estima a própria linha de base observando o sinal:
    leituras próximas do valor recente são tratadas como repouso e
    atualizam a linha de base devagar; saltos abruptos acima do limiar são
    tratados como ciclo de passagem de trem e alimentam Basquin.
    """

    sensor_id: str
    dano_acumulado: float = 0.0
    ciclos_contados: int = 0
    _linha_de_base_n: float | None = field(default=None, repr=False)
    _timestamp_inicial: float | None = field(default=None, repr=False)
    _timestamp_atual: float | None = field(default=None, repr=False)

    @property
    def estado(self) -> str:
        if self.dano_acumulado >= LIMIAR_CRITICO:
            return "CRITICO"
        if self.dano_acumulado >= LIMIAR_ATENCAO:
            return "ATENCAO"
        return "NORMAL"

    @property
    def taxa_dano_por_segundo(self) -> float:
        """Taxa média de acúmulo de dano desde a primeira leitura deste sensor.

        Extrapolação linear simples, não uma janela deslizante: o RUL que
        ela produz é tão bom quanto a suposição de que o desgaste futuro
        segue o ritmo médio observado até agora, o que é razoável para
        detectar mudança de regime (sensor acelerando), mas não captura
        uma virada abrupta que ainda não aconteceu.
        """
        if self._timestamp_inicial is None or self._timestamp_atual is None:
            return 0.0
        decorrido = self._timestamp_atual - self._timestamp_inicial
        if decorrido <= 0:
            return 0.0
        return self.dano_acumulado / decorrido

    def rul_segundos(self) -> float | None:
        """Tempo estimado até `dano_acumulado` cruzar LIMIAR_CRITICO, ou None sem dado suficiente."""
        taxa = self.taxa_dano_por_segundo
        if taxa <= 0.0:
            return None
        restante = max(0.0, LIMIAR_CRITICO - self.dano_acumulado)
        return restante / taxa

    def processar(self, tensao_mecanica_n: float, timestamp: float | None = None) -> None:
        if timestamp is not None:
            if self._timestamp_inicial is None:
                self._timestamp_inicial = timestamp
            self._timestamp_atual = timestamp

        if self._linha_de_base_n is None:
            self._linha_de_base_n = tensao_mecanica_n
            return

        amplitude = tensao_mecanica_n - self._linha_de_base_n
        if amplitude >= LIMIAR_CICLO_N:
            self._registrar_ciclo(amplitude)
        else:
            self._linha_de_base_n += (tensao_mecanica_n - self._linha_de_base_n) * GANHO_LINHA_DE_BASE

    def _registrar_ciclo(self, amplitude_n: float) -> None:
        razao = amplitude_n / TENSAO_REFERENCIA_N
        ciclos_ate_falha = max(1.0, razao**-EXPOENTE_BASQUIN)
        self.dano_acumulado = min(1.0, self.dano_acumulado + 1.0 / ciclos_ate_falha)
        self.ciclos_contados += 1
