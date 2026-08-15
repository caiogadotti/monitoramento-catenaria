// Gateway de ingestão: aceita uma conexão TCP por sensor de catenária e
// agrega as leituras em lotes, prontos para o motor de análise (fase 3).
//
// Rodar:
//
//	go run ./cmd/gateway --porta :9000 --intervalo-lote 1s
package main

import (
	"context"
	"encoding/json"
	"flag"
	"log"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/caiogadotti/monitoramento-catenaria/internal/ingestao"
)

func main() {
	porta := flag.String("porta", ":9000", "endereco TCP para aceitar conexoes de sensor")
	intervaloLote := flag.Duration("intervalo-lote", 1*time.Second, "janela de agregacao de cada lote")
	flag.Parse()

	ctx, cancelar := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer cancelar()

	lotes := make(chan ingestao.Lote, 8)
	servidor := ingestao.NovoServidor(*porta, *intervaloLote, lotes)

	// stdout carrega só dado (uma leitura por linha, mesmo schema NDJSON
	// que o simulador Python produz), para poder ser encadeado direto num
	// pipe: `go run ./cmd/gateway | python scripts/motor_analise.py`.
	// Estatísticas e erros vão para o log, que escreve em stderr por
	// padrão -- os dois fluxos nunca se misturam no mesmo stream.
	go publicarLeituras(lotes)

	if err := servidor.Iniciar(ctx); err != nil {
		log.Fatal(err)
	}
}

func publicarLeituras(lotes <-chan ingestao.Lote) {
	codificador := json.NewEncoder(os.Stdout)

	for lote := range lotes {
		for _, leitura := range lote.Leituras {
			if err := codificador.Encode(leitura); err != nil {
				log.Printf("erro ao publicar leitura: %v", err)
			}
		}
	}
}
