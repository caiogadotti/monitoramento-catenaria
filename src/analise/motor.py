"""Motor de análise: decide o risco de cada sensor a partir de leituras cruas.

Mantém um `AcumuladorDano` por sensor (estimativa por contagem de ciclos,
via Basquin/Miner) e cruza com a estimativa espectral independente (via
FFT). Nenhuma das duas nunca lê o `dano_acumulado` que o simulador já
sabe: esse campo só entra depois, na validação, para medir o quão perto as
duas estimativas independentes chegam da verdade conhecida.

**Por que o estado sai do maior dos dois, e não da contagem de ciclos.**
A primeira versão deste módulo usava `estado=acumulador.estado`, ou seja,
só a contagem de ciclos. Um teste de ponta a ponta expôs o furo: um sensor
com dano real de 0.652, a um passo do limiar crítico de 0.7, foi
classificado como NORMAL e não disparou alerta nenhum, porque a contagem
de ciclos estimou 0.049. O estimador espectral, no mesmo instante, dizia
0.609.

A causa não é um erro de conta a corrigir: a contagem de ciclos é cega
para desgaste acelerado por construção (ver `AcumuladorDano`), e nenhum
sensor real conheceria a taxa de desgaste do próprio ponto. Os 2% de
pontos que se degradam de 8 a 20 vezes mais rápido são justamente os que
vão falhar primeiro, e eram invisíveis para a lógica de alerta. Usar o
maior dos dois é a leitura conservadora correta num sistema cuja função é
avisar antes da falha.

A divergência entre os dois estimadores deixou de ser ruído e virou sinal:
ela é a assinatura de desgaste acelerado, e por isso vira um campo próprio
na avaliação.

**Por que o sinal espectral é usado de duas formas aqui.** O estado sai do
valor suavizado por média móvel (ver `SuavizadorEspectral`), porque a
estimativa por janela isolada oscila em torno do limiar e gerava alerta
repetido para o mesmo ponto. Já a divergência é medida no valor **cru**.
Essa separação não é gratuita, saiu de medição: suavizar comprime os picos
que denunciam desgaste acelerado, e num teste de 150 sensores a divergência
máxima do sensor defeituoso mais fraco caía de 0.188 para 0.069, ficando
indistinguível dos saudáveis (0.066). No sinal cru esse mesmo sensor fica
em 0.188 contra 0.059 do pior saudável, uma margem confortável. Cada uso
fica com a versão do sinal em que ele rende: o alerta quer estabilidade, a
detecção de desgaste acelerado quer sensibilidade.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.analise.espectro import (
    JANELAS_SUAVIZACAO,
    SuavizadorEspectral,
    estimar_dano_espectral,
    estimar_snr_db,
)
from src.analise.fadiga import AcumuladorDano, classificar_estado

# Acima dessa diferença entre as duas estimativas, o ponto é tratado como
# suspeito de desgaste acelerado. Calibrado com folga: num teste com 10
# sensores, os 9 saudáveis ficaram abaixo de 0.009 de divergência e o
# defeituoso ficou em 0.56. Qualquer corte entre 0.05 e 0.4 separaria os
# dois casos; 0.15 fica longe das duas pontas.
LIMIAR_DIVERGENCIA = 0.15


@dataclass
class Avaliacao:
    sensor_id: str
    km: float
    dano_ciclos: float
    dano_espectral: float
    estado: str
    ciclos_contados: int
    snr_db: float
    rul_segundos: float | None
    desgaste_acelerado: bool
    dano_espectral_bruto: float

    @property
    def dano(self) -> float:
        """Dano oficial do ponto: a leitura conservadora entre as duas estimativas."""
        return max(self.dano_ciclos, self.dano_espectral)

    @property
    def divergencia(self) -> float:
        """Distância entre os dois estimadores, medida no sinal espectral cru.

        Usa o valor sem suavização de propósito, ver a nota sobre os dois
        usos do sinal espectral na docstring do módulo.
        """
        return abs(self.dano_ciclos - self.dano_espectral_bruto)


class MotorAnalise:
    def __init__(self, janelas_suavizacao: int = JANELAS_SUAVIZACAO) -> None:
        self._acumuladores: dict[str, AcumuladorDano] = {}
        self._suavizadores: dict[str, SuavizadorEspectral] = {}
        self._janelas_suavizacao = janelas_suavizacao

    def processar_leitura(self, leitura: dict) -> Avaliacao:
        sensor_id = leitura["sensor_id"]
        acumulador = self._acumuladores.setdefault(sensor_id, AcumuladorDano(sensor_id))
        acumulador.processar(leitura["tensao_mecanica_n"], leitura.get("timestamp"))

        suavizador = self._suavizadores.setdefault(
            sensor_id, SuavizadorEspectral(self._janelas_suavizacao)
        )

        vibracao = leitura["vibracao"]
        dano_espectral_bruto = estimar_dano_espectral(vibracao)
        dano_espectral = suavizador.suavizar(dano_espectral_bruto)
        dano_ciclos = acumulador.dano_acumulado

        return Avaliacao(
            sensor_id=sensor_id,
            km=leitura.get("km", 0.0),
            dano_ciclos=dano_ciclos,
            dano_espectral=dano_espectral,
            estado=classificar_estado(max(dano_ciclos, dano_espectral)),
            ciclos_contados=acumulador.ciclos_contados,
            snr_db=estimar_snr_db(vibracao),
            rul_segundos=acumulador.rul_segundos(),
            desgaste_acelerado=abs(dano_ciclos - dano_espectral_bruto) >= LIMIAR_DIVERGENCIA,
            dano_espectral_bruto=dano_espectral_bruto,
        )
