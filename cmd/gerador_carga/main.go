// Gerador de carga: abre N conexões TCP concorrentes contra o gateway e
// envia leituras sintéticas em cada uma, para provar (não só afirmar) que
// o gateway aguenta milhares de sensores publicando ao mesmo tempo.
//
// Rodar:
//
//	go run ./cmd/gerador_carga --sensores 2000 --alvo 127.0.0.1:9000 --duracao 10s
package main

import (
	"encoding/json"
	"flag"
	"fmt"
	"log"
	"net"
	"sync"
	"sync/atomic"
	"time"

	"github.com/caiogadotti/monitoramento-catenaria/internal/ingestao"
)

func main() {
	sensores := flag.Int("sensores", 2000, "numero de conexoes concorrentes a abrir")
	// IPv4 explicito, nao "localhost": em Windows "localhost" resolve para
	// ::1 (IPv6) primeiro, e se o listener do gateway so aceitar IPv4 (caso
	// comum), a maioria das conexoes leva "connection actively refused"
	// mesmo com o gateway rodando perfeitamente.
	alvo := flag.String("alvo", "127.0.0.1:9000", "endereco do gateway")
	duracao := flag.Duration("duracao", 10*time.Second, "por quanto tempo manter as conexoes enviando")
	intervaloEnvio := flag.Duration("intervalo-envio", 1*time.Second, "intervalo entre leituras de um mesmo sensor")
	// disparar 2000 dials no mesmo instante estoura o backlog de conexoes
	// pendentes do SO (nao e um limite do gateway, e do stack TCP local
	// aceitando SYNs mais rapido do que consegue processar). Espalhar as
	// conexoes numa janela pequena resolve, e e mais realista: sensores de
	// verdade tambem nao conectam todos no mesmo microssegundo.
	janelaConexao := flag.Duration("janela-conexao", 3*time.Second, "tempo total para espalhar a abertura das N conexoes")
	flag.Parse()

	var conexoesOk, conexoesFalha, leiturasEnviadas atomic.Int64

	var grupo sync.WaitGroup
	inicio := time.Now()

	atrasoPorSensor := time.Duration(0)
	if *sensores > 1 {
		atrasoPorSensor = *janelaConexao / time.Duration(*sensores)
	}

	for i := 0; i < *sensores; i++ {
		grupo.Add(1)
		atraso := time.Duration(i) * atrasoPorSensor
		go func(indice int, atraso time.Duration) {
			defer grupo.Done()
			time.Sleep(atraso)
			simularSensor(indice, *alvo, *duracao, *intervaloEnvio, &conexoesOk, &conexoesFalha, &leiturasEnviadas)
		}(i, atraso)
	}

	grupo.Wait()
	decorrido := time.Since(inicio)

	fmt.Printf(
		"\n%d sensores simulados em %v (janela de conexao: %v)\n  conexoes ok=%d  falhas=%d  leituras enviadas=%d (%.0f/s)\n",
		*sensores, decorrido, *janelaConexao, conexoesOk.Load(), conexoesFalha.Load(),
		leiturasEnviadas.Load(), float64(leiturasEnviadas.Load())/decorrido.Seconds(),
	)
}

func simularSensor(
	indice int, alvo string, duracao, intervaloEnvio time.Duration,
	conexoesOk, conexoesFalha, leiturasEnviadas *atomic.Int64,
) {
	conexao, err := discarComRetentativa(alvo, 3)
	if err != nil {
		conexoesFalha.Add(1)
		if indice < 5 || indice%500 == 0 { // amostra os erros, nao poluir com milhares de linhas iguais
			log.Printf("sensor %d: falha ao conectar apos retentativas: %v", indice, err)
		}
		return
	}
	defer conexao.Close()
	conexoesOk.Add(1)

	codificador := json.NewEncoder(conexao)
	fim := time.Now().Add(duracao)
	ticker := time.NewTicker(intervaloEnvio)
	defer ticker.Stop()

	for time.Now().Before(fim) {
		leitura := ingestao.Leitura{
			SensorID:        fmt.Sprintf("CARGA-%05d", indice),
			KM:              float64(indice) / 50.0,
			Timestamp:       float64(time.Now().Unix()),
			TensaoMecanicaN: 13000,
			TemperaturaC:    24,
			DanoAcumulado:   0,
			Estado:          "NORMAL",
			Vibracao:        make([]float64, 200), // mesmo tamanho de janela do simulador Python
		}
		if err := codificador.Encode(leitura); err != nil {
			log.Printf("sensor %d: erro ao enviar: %v", indice, err)
			return
		}
		leiturasEnviadas.Add(1)
		<-ticker.C
	}
}

// discarComRetentativa tenta conectar algumas vezes com backoff curto.
// Um SYN perdido no meio de uma rajada de conexoes e transiente por
// natureza -- um sensor real reconectaria, entao o gerador de carga
// tambem deveria, em vez de contar como falha permanente na primeira
// tentativa.
func discarComRetentativa(alvo string, tentativas int) (net.Conn, error) {
	var ultimoErro error
	for tentativa := 1; tentativa <= tentativas; tentativa++ {
		conexao, err := net.DialTimeout("tcp", alvo, 2*time.Second)
		if err == nil {
			return conexao, nil
		}
		ultimoErro = err
		time.Sleep(time.Duration(tentativa) * 100 * time.Millisecond)
	}
	return nil, ultimoErro
}
