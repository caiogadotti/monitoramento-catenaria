"""Roda o motor de análise sobre leituras em NDJSON (stdin ou arquivo).

Consome exatamente o que o gateway em Go produz: uma leitura por linha, no
mesmo schema de LeituraSensor. Nunca lê o campo `dano_acumulado` da leitura
para decidir nada, só no relatório, para validar a estimativa independente
contra o valor que o simulador sabe ser verdadeiro.

Uso:
    # pipeline completo: simulador -> gateway em Go -> motor de analise
    go run ./cmd/gateway --porta :9000 | python scripts/motor_analise.py &
    python scripts/simular_sensores.py --gateway 127.0.0.1:9000 --duracao-s 30

    # ou testando sem rede, direto de um arquivo gerado antes:
    python scripts/simular_sensores.py --duracao-s 30 > leituras.ndjson
    python scripts/motor_analise.py --arquivo leituras.ndjson

    # persistindo no Supabase (precisa de SUPABASE_DB_URL no ambiente):
    python scripts/motor_analise.py --arquivo leituras.ndjson --supabase
"""

import argparse
import datetime
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from src.analise.motor import MotorAnalise


class Estatisticas:
    """Acumula os números do relatório, separado da leitura do stream.

    O gateway roda para sempre (é um servidor), então o pipe entre ele e
    este script nunca fecha sozinho. Sem separar a coleta da impressão,
    o relatório só sairia quando o processo morresse. Com a separação, dá
    para imprimir um resumo compacto a cada N leituras (`--intervalo-relatorio`)
    e ainda assim ter o relatório completo de sempre ao final (arquivo
    finito, ou Ctrl+C no pipe ao vivo).
    """

    def __init__(self) -> None:
        self.total_leituras = 0
        self.alertas_emitidos = 0
        self.estado_anterior: dict[str, str] = {}
        self.erros_ciclos: list[float] = []
        self.erros_espectral: list[float] = []

    def registrar(self, avaliacao, dano_real: float | None) -> bool:
        """Retorna True se essa leitura disparou um alerta novo."""
        self.total_leituras += 1
        if dano_real is not None:
            self.erros_ciclos.append(abs(avaliacao.dano_ciclos - dano_real))
            self.erros_espectral.append(abs(avaliacao.dano_espectral - dano_real))

        anterior = self.estado_anterior.get(avaliacao.sensor_id, "NORMAL")
        disparou = avaliacao.estado != anterior and avaliacao.estado in ("ATENCAO", "CRITICO")
        if disparou:
            self.alertas_emitidos += 1
        self.estado_anterior[avaliacao.sensor_id] = avaliacao.estado
        return disparou

    def imprimir(self, destino, completo: bool) -> None:
        print(f"\nleituras processadas: {self.total_leituras}", file=destino)
        print(f"sensores distintos: {len(self.estado_anterior)}", file=destino)
        print(f"alertas emitidos: {self.alertas_emitidos}", file=destino)

        if completo and self.erros_ciclos:
            media_ciclos = sum(self.erros_ciclos) / len(self.erros_ciclos)
            media_espectral = sum(self.erros_espectral) / len(self.erros_espectral)
            print("\nvalidação contra o dano real do simulador (não usado para decidir nada acima):", file=destino)
            print(f"  erro médio absoluto, estimativa por ciclos (Basquin/Miner): {media_ciclos:.4f}", file=destino)
            print(f"  erro médio absoluto, estimativa espectral (FFT):           {media_espectral:.4f}", file=destino)


def main() -> None:
    parser = argparse.ArgumentParser(description="Motor de análise de fadiga de catenária")
    parser.add_argument("--arquivo", type=str, default=None, help="lê NDJSON de um arquivo em vez de stdin")
    parser.add_argument(
        "--silencioso", action="store_true", help="não imprime cada alerta, só os resumos"
    )
    parser.add_argument(
        "--intervalo-relatorio", type=int, default=500,
        help="a cada quantas leituras imprime um resumo compacto (0 desativa)",
    )
    parser.add_argument(
        "--supabase", action="store_true",
        help="persiste leituras e alertas no Postgres do Supabase (requer SUPABASE_DB_URL)",
    )
    parser.add_argument(
        "--lote-supabase", type=int, default=50,
        help="quantas leituras acumular antes de gravar em lote no Supabase",
    )
    args = parser.parse_args()

    origem = open(args.arquivo, encoding="utf-8") if args.arquivo else sys.stdin

    motor = MotorAnalise()
    estatisticas = Estatisticas()

    conexao_supabase = None
    lote_leituras: list[tuple] = []
    if args.supabase:
        from src.persistencia.supabase import abrir_conexao, gravar_alerta, gravar_leituras_lote

        conexao_supabase = abrir_conexao()

    def _flush_lote() -> None:
        if lote_leituras:
            gravar_leituras_lote(conexao_supabase, lote_leituras)
            lote_leituras.clear()

    try:
        for linha in origem:
            linha = linha.strip()
            if not linha or linha.startswith("#"):
                continue

            leitura = json.loads(linha)
            avaliacao = motor.processar_leitura(leitura)
            disparou_alerta = estatisticas.registrar(avaliacao, leitura.get("dano_acumulado"))

            if disparou_alerta and not args.silencioso:
                rul_txt = f"{avaliacao.rul_segundos:.0f}s" if avaliacao.rul_segundos is not None else "n/d"
                print(
                    f"ALERTA {avaliacao.estado:8s} sensor={avaliacao.sensor_id}  "
                    f"km={avaliacao.km:.2f}  dano_ciclos={avaliacao.dano_ciclos:.3f}  "
                    f"dano_espectral={avaliacao.dano_espectral:.3f}  "
                    f"snr={avaliacao.snr_db:.1f}dB  rul={rul_txt}",
                    file=sys.stderr,
                )

            if conexao_supabase is not None:
                lote_leituras.append((
                    avaliacao.sensor_id,
                    avaliacao.km,
                    datetime.datetime.fromtimestamp(leitura["timestamp"], tz=datetime.timezone.utc),
                    leitura["tensao_mecanica_n"],
                    leitura["temperatura_c"],
                    avaliacao.dano_ciclos,
                    avaliacao.dano_espectral,
                    avaliacao.snr_db,
                    avaliacao.rul_segundos,
                    avaliacao.estado,
                    avaliacao.ciclos_contados,
                ))
                if len(lote_leituras) >= args.lote_supabase:
                    _flush_lote()
                if disparou_alerta:
                    gravar_alerta(
                        conexao_supabase, avaliacao.sensor_id, avaliacao.km,
                        avaliacao.estado, avaliacao.dano_ciclos, avaliacao.dano_espectral,
                    )

            if args.intervalo_relatorio and estatisticas.total_leituras % args.intervalo_relatorio == 0:
                estatisticas.imprimir(sys.stderr, completo=False)
    finally:
        if conexao_supabase is not None:
            _flush_lote()
            conexao_supabase.close()
        if args.arquivo:
            origem.close()

    estatisticas.imprimir(sys.stdout, completo=True)


if __name__ == "__main__":
    main()
