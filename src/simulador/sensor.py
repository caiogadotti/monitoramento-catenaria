"""Modelo físico de um ponto de sensor na rede de catenária.

Cada ponto acumula dano por fadiga a cada passagem de trem (regra de
Palmgren-Miner: dano de cada ciclo soma linearmente até o limiar de
falha). O sinal de vibração que o sensor "lê" muda com esse dano
acumulado, o mesmo jeito que microtrincas reais alteram a resposta
vibracional de um cabo antes da falha visível.

Valores de tensão, amplitude e limiares são ilustrativos, calibrados
para o dano evoluir de forma visível ao longo de uma simulação de
minutos, não para reproduzir um cabo real. Ver a ressalva no README.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

TAXA_AMOSTRAGEM_HZ = 200
JANELA_SEGUNDOS = 1.0
AMOSTRAS_POR_JANELA = int(TAXA_AMOSTRAGEM_HZ * JANELA_SEGUNDOS)

FREQUENCIA_ESTRUTURAL_HZ = 18.0  # ressonância típica de cabo tensionado
FREQUENCIA_REDE_HZ = 60.0  # acoplamento da rede elétrica de tração

# regra de Basquin simplificada: ciclos_ate_falha = (tensao_ref / amplitude_ciclo) ** expoente
#
# Os dois valores abaixo são acelerados de propósito, não são o dado real
# de catálogo. Ver TENSAO_REFERENCIA_REAL_N e EXPOENTE_BASQUIN_REAL logo
# abaixo para os números reais publicados e por que não são o padrão.
TENSAO_REFERENCIA_N = 14000.0
EXPOENTE_BASQUIN = 6.0

# --- Valores reais, citados, para referência e para o experimento de
# --- comparação (scripts/comparar_regime_real.py). Não são o padrão
# --- porque, usados de fato, o dano leva dias reais para evoluir, o que
# --- inviabiliza a demonstração interativa deste projeto.
#
# TENSAO_REFERENCIA_REAL_N: tensão mecânica real de fio de contato fica
# entre 15 e 30 kN, dependendo da classe de velocidade da linha
# (Railway Energy: Overhead Contact Line System, RailBaltica Design
# Manual; He, Guo & Chen, "Numerical study of contact wire tension
# affecting dropper stress of a catenary system", Advances in Mechanical
# Engineering, 2021). 20 kN é um valor representativo de linha
# intercidades (nem o extremo de alta velocidade acima de 250km/h, nem
# o mínimo de linha convencional lenta).
TENSAO_REFERENCIA_REAL_N = 20000.0

# EXPOENTE_BASQUIN_REAL: o expoente de Basquin $b$ para metais fica entre
# -0.05 e -0.12 (faixa estabelecida na literatura de fadiga de
# materiais). Com EXPOENTE_BASQUIN = -1/b neste código, isso equivale a
# um expoente entre 8.3 e 20. Usamos 10 (b ≈ -0.10, meio da faixa) como
# valor representativo, não específico de liga de cobre: não encontrei
# acesso público ao $\sigma'_f$ e $b$ medidos especificamente para fio
# de contato Cu-Mg/Cu-Ag (haveria em Yang et al., "Bending fatigue life
# evaluation of Cu-Mg alloy contact wire", Int. J. Precis. Eng. Manuf.,
# 2014, atrás de paywall no momento em que isso foi escrito).
EXPOENTE_BASQUIN_REAL = 10.0

LIMIAR_ATENCAO = 0.3
LIMIAR_CRITICO = 0.7


@dataclass
class LeituraSensor:
    sensor_id: str
    km: float
    timestamp: float
    tensao_mecanica_n: float
    temperatura_c: float
    dano_acumulado: float
    estado: str
    vibracao: list[float]  # amostras brutas da janela, para o motor de análise fazer FFT depois


@dataclass
class PontoSensor:
    """Um ponto de monitoramento fixo ao longo da linha.

    `taxa_desgaste` controla o quão rápido esse ponto específico acumula
    dano por passagem de trem. Pontos com taxa mais alta simulam
    catenária mais antiga ou com defeito de instalação, e é isso que
    o motor de análise (próxima fase) precisa aprender a distinguir dos
    pontos saudáveis só olhando o sinal de vibração.
    """

    sensor_id: str
    km: float
    taxa_desgaste: float = 1.0
    tensao_base_n: float = 13000.0
    _dano_acumulado: float = field(default=0.0, repr=False)
    _rng: np.random.Generator = field(default_factory=np.random.default_rng, repr=False)

    @property
    def dano_acumulado(self) -> float:
        return min(self._dano_acumulado, 1.0)

    @property
    def estado(self) -> str:
        if self.dano_acumulado >= LIMIAR_CRITICO:
            return "CRITICO"
        if self.dano_acumulado >= LIMIAR_ATENCAO:
            return "ATENCAO"
        return "NORMAL"

    def registrar_passagem_de_trem(
        self,
        amplitude_tensao_n: float,
        tensao_referencia_n: float = TENSAO_REFERENCIA_N,
        expoente_basquin: float = EXPOENTE_BASQUIN,
    ) -> None:
        """Cada passagem gera um ciclo de tensão que consome uma fração da vida do cabo.

        `amplitude_tensao_n` é o pico de tensão mecânica acima da tensão base durante
        a passagem (peso do trem + dinâmica de contato do pantógrafo). A fração de
        dano por ciclo vem da regra de Basquin: quanto maior a amplitude relativa à
        tensão de referência, menos ciclos o cabo aguenta até a falha, logo mais dano
        por ciclo.

        `tensao_referencia_n` e `expoente_basquin` têm os valores acelerados da
        demo como padrão; passar `TENSAO_REFERENCIA_REAL_N` e
        `EXPOENTE_BASQUIN_REAL` roda a mesma física com os números reais
        citados no topo deste módulo (ver `scripts/comparar_regime_real.py`).
        """
        razao = amplitude_tensao_n / tensao_referencia_n
        ciclos_ate_falha = max(1.0, razao**-expoente_basquin)
        dano_por_ciclo = (1.0 / ciclos_ate_falha) * self.taxa_desgaste
        self._dano_acumulado += dano_por_ciclo

    def _sintetizar_vibracao(self, tensao_instantanea_n: float, temperatura_c: float) -> np.ndarray:
        """Gera a janela de vibração que um acelerômetro real produziria neste instante.

        Três componentes se somam:
        1. Oscilação estrutural na frequência de ressonância do cabo, com amplitude
           proporcional à tensão mecânica instantânea (cabo mais esticado vibra mais forte).
        2. Acoplamento de 60 Hz da rede de tração, presente em qualquer ponto próximo
           à linha energizada, independente do estado do cabo.
        3. Ruído de banda larga cuja intensidade cresce com o dano acumulado, simulando
           o efeito de folga mecânica e microfraturas que uma catenária degradada
           introduz na resposta vibracional. É esse crescimento que o motor de análise
           terá que detectar via densidade espectral, não a amplitude bruta sozinha.
        """
        t = np.arange(AMOSTRAS_POR_JANELA) / TAXA_AMOSTRAGEM_HZ

        amplitude_estrutural = 0.4 + (tensao_instantanea_n / TENSAO_REFERENCIA_N) * 0.6
        sinal = amplitude_estrutural * np.sin(2 * math.pi * FREQUENCIA_ESTRUTURAL_HZ * t)

        sinal += 0.15 * np.sin(2 * math.pi * FREQUENCIA_REDE_HZ * t)

        intensidade_ruido = 0.05 + self.dano_acumulado * 0.6
        sinal += self._rng.normal(0, intensidade_ruido, AMOSTRAS_POR_JANELA)

        deriva_termica = (temperatura_c - 25.0) * 0.004
        sinal += deriva_termica

        return sinal

    def ler(self, timestamp: float, passagem_de_trem: bool, temperatura_c: float) -> LeituraSensor:
        tensao_instantanea = self.tensao_base_n
        if passagem_de_trem:
            amplitude = self._rng.uniform(3000, 9000)
            tensao_instantanea += amplitude
            self.registrar_passagem_de_trem(amplitude)

        vibracao = self._sintetizar_vibracao(tensao_instantanea, temperatura_c)

        return LeituraSensor(
            sensor_id=self.sensor_id,
            km=self.km,
            timestamp=timestamp,
            tensao_mecanica_n=round(float(tensao_instantanea), 1),
            temperatura_c=round(temperatura_c, 1),
            dano_acumulado=round(self.dano_acumulado, 5),
            estado=self.estado,
            vibracao=[round(float(v), 4) for v in vibracao],
        )
