package ingestao

import (
	"bufio"
	"context"
	"encoding/json"
	"fmt"
	"log"
	"net"
	"sync/atomic"
	"time"
)

// Servidor aceita uma conexão TCP por sensor e agrega as leituras recebidas.
//
// A decisão central de arquitetura mora aqui: cada conexão vira sua própria
// goroutine em aceitarConexoes, lendo linha por linha sem bloquear as
// outras. Todas elas escrevem no mesmo canal `leituras`, e só uma goroutine
// (agregar) lê desse canal — é o canal, não um mutex, que serializa o
// acesso ao estado compartilhado. Não existe lock manual em lugar nenhum
// deste pacote, porque não precisa existir.
type Servidor struct {
	Porta         string
	TamanhoBuffer int           // capacidade do canal de leituras, absorve picos de burst
	IntervaloLote time.Duration // de quanto em quanto tempo um lote agregado é fechado
	SaidaLotes    chan<- Lote   // para onde os lotes agregados vão (o motor de análise, fase 3)

	leituras chan Leitura

	conexoesAtivas atomic.Int64
	leiturasTotais atomic.Int64
	conexoesTotais atomic.Int64
}

// Lote é o resultado de uma janela de agregação: todas as leituras
// recebidas de todos os sensores naquele intervalo, prontas para o motor
// de análise em Python processar.
type Lote struct {
	FechadoEm time.Time
	Leituras  []Leitura
}

func NovoServidor(porta string, intervaloLote time.Duration, saidaLotes chan<- Lote) *Servidor {
	return &Servidor{
		Porta:         porta,
		TamanhoBuffer: 10_000, // milhares de sensores podem publicar no mesmo instante
		IntervaloLote: intervaloLote,
		SaidaLotes:    saidaLotes,
		leituras:      make(chan Leitura, 10_000),
	}
}

// Iniciar sobe o listener TCP e bloqueia até o contexto ser cancelado.
func (s *Servidor) Iniciar(ctx context.Context) error {
	listener, err := net.Listen("tcp", s.Porta)
	if err != nil {
		return fmt.Errorf("abrindo porta %s: %w", s.Porta, err)
	}
	defer listener.Close()

	log.Printf("gateway ouvindo em %s", s.Porta)

	go s.agregar(ctx)
	go s.relatarEstatisticas(ctx)

	go func() {
		<-ctx.Done()
		listener.Close()
	}()

	for {
		conexao, err := listener.Accept()
		if err != nil {
			select {
			case <-ctx.Done():
				return nil
			default:
				log.Printf("erro ao aceitar conexão: %v", err)
				continue
			}
		}

		s.conexoesTotais.Add(1)
		go s.tratarConexao(conexao)
	}
}

// tratarConexao roda numa goroutine própria por sensor conectado. Uma
// leitura demorada ou um sensor travado nunca bloqueia os outros milhares
// de conexões, porque cada uma tem sua própria goroutine e sua própria
// pilha, não compartilha nada além do canal de saída.
func (s *Servidor) tratarConexao(conexao net.Conn) {
	defer conexao.Close()
	s.conexoesAtivas.Add(1)
	defer s.conexoesAtivas.Add(-1)

	leitor := bufio.NewScanner(conexao)
	leitor.Buffer(make([]byte, 0, 64*1024), 1024*1024) // janelas de vibração podem passar o buffer padrao de 64KB

	for leitor.Scan() {
		var leitura Leitura
		if err := json.Unmarshal(leitor.Bytes(), &leitura); err != nil {
			log.Printf("linha invalida de %s: %v", conexao.RemoteAddr(), err)
			continue
		}
		s.leituras <- leitura
		s.leiturasTotais.Add(1)
	}
}

// agregar é a única goroutine que consome o canal de leituras. Fecha um
// lote a cada IntervaloLote e o repassa para SaidaLotes, seja qual for o
// consumidor do outro lado (por enquanto, o main imprime; na fase 3, o
// motor de análise em Python).
func (s *Servidor) agregar(ctx context.Context) {
	ticker := time.NewTicker(s.IntervaloLote)
	defer ticker.Stop()

	loteAtual := make([]Leitura, 0, 4096)

	fecharLote := func() {
		if len(loteAtual) == 0 {
			return
		}
		lote := Lote{FechadoEm: time.Now(), Leituras: loteAtual}
		if s.SaidaLotes != nil {
			s.SaidaLotes <- lote
		}
		loteAtual = make([]Leitura, 0, 4096)
	}

	for {
		select {
		case <-ctx.Done():
			fecharLote()
			return
		case leitura := <-s.leituras:
			loteAtual = append(loteAtual, leitura)
		case <-ticker.C:
			fecharLote()
		}
	}
}

func (s *Servidor) relatarEstatisticas(ctx context.Context) {
	ticker := time.NewTicker(5 * time.Second)
	defer ticker.Stop()

	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			log.Printf(
				"conexoes ativas=%d  conexoes totais=%d  leituras recebidas=%d",
				s.conexoesAtivas.Load(), s.conexoesTotais.Load(), s.leiturasTotais.Load(),
			)
		}
	}
}
