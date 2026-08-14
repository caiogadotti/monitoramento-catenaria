"""Roda a rede de sensores simulada e imprime as leituras em NDJSON.

Uso:
    python scripts/simular_sensores.py                          # 40km, 50 sensores/km, para stdout
    python scripts/simular_sensores.py --extensao-km 5 --sensores-por-km 10
    python scripts/simular_sensores.py --duracao-s 30 --intervalo-s 1 > leituras.ndjson
    python scripts/simular_sensores.py --resumo               # só imprime a evolução do estado da rede

Cada linha da saída é um objeto JSON de uma leitura (`src/simulador/sensor.py:LeituraSensor`),
pronta para ser consumida linha a linha pelo gateway em Go da próxima fase.
"""

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from src.simulador.rede import ConfiguracaoRede, RedeCatenaria
from src.simulador.transporte import escrever_ndjson


def main() -> None:
    parser = argparse.ArgumentParser(description="Simulador de sensores de catenária")
    parser.add_argument("--extensao-km", type=float, default=40.0)
    parser.add_argument("--sensores-por-km", type=int, default=50)
    parser.add_argument("--fracao-degradados", type=float, default=0.02)
    parser.add_argument("--intervalo-trens-s", type=float, default=6.0)
    parser.add_argument("--duracao-s", type=float, default=60.0)
    parser.add_argument("--intervalo-s", type=float, default=1.0, help="intervalo entre janelas de leitura")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--resumo", action="store_true", help="imprime só a contagem de estados por janela, não o NDJSON completo"
    )
    args = parser.parse_args()

    config = ConfiguracaoRede(
        extensao_km=args.extensao_km,
        sensores_por_km=args.sensores_por_km,
        fracao_pontos_degradados=args.fracao_degradados,
        intervalo_trens_s=args.intervalo_trens_s,
        seed=args.seed,
    )
    rede = RedeCatenaria(config)

    total_sensores = len(rede.pontos)
    print(
        f"# rede: {total_sensores} sensores em {args.extensao_km}km "
        f"({args.fracao_degradados:.0%} com desgaste acelerado, seed={args.seed})",
        file=sys.stderr,
    )

    inicio = time.time()
    while time.time() - inicio < args.duracao_s:
        leituras = rede.ler_janela()

        if args.resumo:
            estado = rede.resumo_estado()
            decorrido = time.time() - inicio
            print(f"t={decorrido:6.1f}s  NORMAL={estado['NORMAL']:5d}  "
                  f"ATENCAO={estado['ATENCAO']:4d}  CRITICO={estado['CRITICO']:4d}")
        else:
            escrever_ndjson(leituras)

        time.sleep(args.intervalo_s)


if __name__ == "__main__":
    main()
