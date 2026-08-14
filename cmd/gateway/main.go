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

	// enquanto o motor de analise (fase 3) nao existe, o main so descreve
	// cada lote fechado -- a interface (canal de Lote) e o que importa,
	// nao quem consome do outro lado
	go imprimirResumoDosLotes(lotes)

	if err := servidor.Iniciar(ctx); err != nil {
		log.Fatal(err)
	}
}

func imprimirResumoDosLotes(lotes <-chan ingestao.Lote) {
	codificador := json.NewEncoder(os.Stdout)

	for lote := range lotes {
		criticos := 0
		for _, leitura := range lote.Leituras {
			if leitura.Estado == "CRITICO" {
				criticos++
			}
		}

		codificador.Encode(map[string]any{
			"fechado_em":        lote.FechadoEm.Format(time.RFC3339),
			"leituras_no_lote":  len(lote.Leituras),
			"sensores_criticos": criticos,
		})
	}
}
