"""Motor de análise: decide o risco de cada sensor a partir de leituras cruas.

Mantém um `AcumuladorDano` por sensor (a estimativa "oficial", baseada em
ciclos de tensão via Basquin/Miner) e cruza com a estimativa espectral
independente (via FFT) a cada leitura, como uma segunda opinião. Nenhuma
das duas nunca lê o `dano_acumulado` que o simulador já sabe: esse campo
só entra depois, na validação, para medir o quão perto as duas
estimativas independentes chegam da verdade conhecida.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.analise.espectro import estimar_dano_espectral, estimar_snr_db
from src.analise.fadiga import AcumuladorDano


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


class MotorAnalise:
    def __init__(self) -> None:
        self._acumuladores: dict[str, AcumuladorDano] = {}

    def processar_leitura(self, leitura: dict) -> Avaliacao:
        sensor_id = leitura["sensor_id"]
        acumulador = self._acumuladores.setdefault(sensor_id, AcumuladorDano(sensor_id))
        acumulador.processar(leitura["tensao_mecanica_n"], leitura.get("timestamp"))

        vibracao = leitura["vibracao"]
        dano_espectral = estimar_dano_espectral(vibracao)
        snr_db = estimar_snr_db(vibracao)

        return Avaliacao(
            sensor_id=sensor_id,
            km=leitura.get("km", 0.0),
            dano_ciclos=acumulador.dano_acumulado,
            dano_espectral=dano_espectral,
            estado=acumulador.estado,
            ciclos_contados=acumulador.ciclos_contados,
            snr_db=snr_db,
            rul_segundos=acumulador.rul_segundos(),
        )
