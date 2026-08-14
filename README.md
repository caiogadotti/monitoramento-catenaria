<div align="center">

# Monitoramento Preditivo de Catenária

**Da prancheta de AutoCAD ao sensor: monitoramento de fadiga estrutural em redes de catenária ferroviária.**

Gateway de ingestão concorrente em Go recebendo telemetria de milhares de pontos
de sensor simultâneos, com um motor de análise em Python que cruza vibração
mecânica com um modelo simplificado de fadiga estrutural para prever pontos de
falha antes que aconteçam.

[![Go](https://img.shields.io/badge/Go-00ADD8?logo=go&logoColor=white)](https://go.dev)
[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)](https://www.python.org)
[![Streamlit](https://img.shields.io/badge/Streamlit-FF4B4B?logo=streamlit&logoColor=white)](https://streamlit.io)
[![Supabase](https://img.shields.io/badge/Supabase-3FCF8E?logo=supabase&logoColor=white)](https://supabase.com)

`Em desenvolvimento`

**Português** &nbsp;·&nbsp; [English](README.en.md)

</div>

---

## Por que esse projeto

Antes de programar, passei 6 meses na Systra, multinacional de engenharia
ferroviária, trabalhando em projetos de infraestrutura para o Trem
Intercidades de São Paulo (TIC). Nesse período produzi desenhos técnicos e
esquemas de controle de sistemas de catenária em AutoCAD, o cabo suspenso
sobre a via que transmite energia para o trem por contato com o pantógrafo.

Catenária é infraestrutura crítica sob estresse mecânico constante: tensão
de tração, vibração da passagem do trem, variação térmica, desgaste por
contato. Uma falha não avisa antes de acontecer, ela se acumula em ciclos de
fadiga ao longo de meses. Esse projeto pega o problema que eu via representado
em planta baixa e o transforma no problema de engenharia de software real por
trás dele: como um sistema teria que ser desenhado para captar isso em tempo
real, numa escala de milhares de pontos de sensor ao longo de uma linha
inteira, sem perder dado sob carga.

Isso não tem a pretensão de virar produto de engenharia estrutural
certificado. A intenção aqui é mostrar que sei desenhar o pipeline de dados
que um problema de infraestrutura ferroviária real exigiria, do sensor até
a decisão.

---

## O problema, formulado como engenharia

> Entrada: leituras contínuas de vibração de milhares de pontos de sensor ao
> longo da rede de catenária. Saída: uma classificação de risco por ponto
> (normal, atenção, crítico), atualizada em tempo real, sem gargalo de
> ingestão mesmo sob picos de milhares de mensagens por segundo.

Calcular fadiga é a parte fácil. O que a maioria dos protótipos acadêmicos
ignora é o problema de sistemas escondido atrás disso: **ingestão
concorrente em escala**. Um scraper Python single-threaded lendo sensor por
sensor não aguenta uma linha ferroviária inteira. É aí que a escolha de
linguagem deixa de ser estética e vira decisão de engenharia.

---

## Arquitetura

```
milhares de sensores (simulados)
        │  publicam leituras de vibração
        ▼
┌───────────────────────┐
│   Gateway de Ingestão   │  Go, uma goroutine por conexão de sensor,
│         (Go)            │  agregação concorrente via channels
└───────────┬─────────────┘
            │  lotes agregados
            ▼
┌───────────────────────┐
│   Motor de Análise       │  Python, FFT do sinal de vibração,
│      (Python)            │  modelo de acúmulo de fadiga (regra de Basquin
│                          │  simplificada), classificação de risco
└───────────┬─────────────┘
            │  leituras + alertas
            ▼
┌───────────────────────┐
│      Supabase             │  Postgres, histórico de leituras,
│    (Postgres)            │  alertas, pontos de sensor cadastrados
└───────────┬─────────────┘
            │
            ▼
┌───────────────────────┐
│      Dashboard             │  Streamlit, mapa da linha, ranking de
│      (Streamlit)          │  pontos críticos, série temporal de vibração
└───────────────────────┘
```

| Camada | Linguagem | Por que essa escolha |
|---|---|---|
| Gateway de ingestão | **Go** | Milhares de sensores publicando simultaneamente é um problema de concorrência, não de cálculo. Goroutines lidam com milhares de conexões simultâneas com uma fração do custo de memória de threads tradicionais, e channels dão um jeito seguro de agregar leituras de múltiplas goroutines sem lock manual espalhado pelo código. Se esse gateway fosse escrito em Python, o GIL viraria gargalo exatamente na hora que mais importa: pico de tráfego. |
| Motor de análise | **Python** (NumPy, SciPy) | Análise espectral de vibração e o modelo de fadiga são contas, não I/O concorrente. É onde a densidade matemática das bibliotecas científicas do Python compensa, sem o overhead de escrever álgebra linear à mão em Go. |
| Persistência | **Supabase** (Postgres) | Mesma stack que já uso em produção. Histórico de leituras vira uma tabela simples, alertas outra, com relação direta entre elas. |
| Visualização | **Streamlit** | Prototipagem rápida de dashboard sem escrever frontend à mão, mesma escolha dos outros dois projetos deste portfólio. |

---

## O modelo de fadiga, com uma ressalva importante

O acúmulo de dano estrutural aqui usa uma versão simplificada da **regra de
Basquin** (relação entre amplitude de tensão cíclica e número de ciclos até
falha), combinada com a **regra de Palmgren-Miner** para somar o dano de
ciclos de amplitude variável. É o mesmo princípio usado em engenharia de
fadiga de verdade, mas calibrado com parâmetros de exemplo, não com dados de
ensaio de material real do cabo de catenária.

**Isso não substitui uma análise estrutural certificada.** O número final
que o modelo cospe importa menos do que a arquitetura que o produz. O
pipeline de ingestão, processamento e decisão é o mesmo formato que um
sistema de monitoramento real usaria, só que com um modelo físico
simplificado no lugar de dados de ensaio proprietários.

---

## Estado atual

| Componente | Status |
|---|---|
| Simulador de sensores | Planejado |
| Gateway de ingestão (Go) | Planejado |
| Motor de análise (Python) | Planejado |
| Persistência (Supabase) | Planejado |
| Dashboard (Streamlit) | Planejado |

Este README documenta a arquitetura antes da primeira linha de código, de
propósito: desenhar o pipeline primeiro, para todo componente ter um contrato
de entrada e saída definido antes de existir.

---

## Estrutura do projeto

```
├── cmd/gateway/       gateway de ingestão em Go
├── src/                motor de análise em Python
├── scripts/             simulador de sensores e utilitários
└── docs/
```

---

## Créditos

**Disciplina:** Laboratório Computacional de Aprendizado de Máquina (LCML), 2026/2
**Turma:** CIB-NA8
**Professor:** Reinaldo Augusto de Oliveira Ramos

Domínio do problema baseado em experiência profissional de 6 meses na
Systra, em projetos de infraestrutura para o Trem Intercidades de São Paulo
(TIC).
