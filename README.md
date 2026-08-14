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
contato. Uma falha se acumula em silêncio, em ciclos de fadiga ao longo de
meses, até romper sem aviso prévio. Esse projeto pega o problema que eu via representado
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

## O modelo de fadiga

### O fenômeno físico

Fadiga é a degradação estrutural que acontece sob carregamento cíclico:
forças que sobem e descem repetidamente. Mesmo quando cada ciclo fica bem
abaixo do limite de ruptura do material, a repetição cria microfissuras que
se propagam aos poucos até a peça não aguentar mais a carga, e a ruptura
acontece de forma súbita, não gradual. É por isso que fadiga é perigosa: o
cabo pode parecer intacto até o ciclo exato em que rompe.

### Regra de Basquin: quantos ciclos até a falha

Proposta por O. H. Basquin em 1910, descreve a relação entre a amplitude de
tensão cíclica e o número de ciclos que o material aguenta antes de falhar,
no regime elástico (sem deformação plástica visível):

$$\sigma_a = \sigma'_f \, (2N_f)^b$$

| Símbolo | Significado |
|---|---|
| $\sigma_a$ | amplitude da tensão do ciclo |
| $\sigma'_f$ | coeficiente de resistência à fadiga do material (de ensaio real) |
| $N_f$ | número de ciclos até a falha |
| $b$ | expoente de Basquin, negativo, inclinação da curva na escala log-log |

### Regra de Palmgren-Miner: somando ciclos de amplitude variável

Basquin sozinho responde a pergunta certa só para tensão constante. Um cabo
de catenária de verdade sofre tensões variáveis: uma rajada de vento gera
ciclos fortes, uma brisa gera ciclos fracos. Palmgren (1924) e Miner (1945)
propuseram, cada um de forma independente, que o dano é linear, cumulativo
e irreversível: cada ciclo consome uma fração da vida útil, e a falha
acontece quando essas frações somam 1:

$$D = \sum_{i=1}^{k} \frac{n_i}{N_i} \qquad \text{falha quando } D \geq 1$$

Onde $n_i$ é quantos ciclos aconteceram no nível de tensão $i$, e $N_i$ é
quantos ciclos aquele nível de tensão aguentaria até falhar (Basquin
responde isso).

### Como isso vira código

| Símbolo da teoria | Onde está em `sensor.py` |
|---|---|
| $\sigma_a$ | `amplitude_tensao_n`, o pico de tensão de cada passagem de trem |
| $\sigma'_f$ | `TENSAO_REFERENCIA_N` |
| $b$ (na forma $N_f = (\sigma_a/\sigma'_f)^{1/b}$) | `EXPOENTE_BASQUIN`, com $1/b = -\text{EXPOENTE\_BASQUIN}$ |
| $N_i$ | `ciclos_ate_falha`, calculado a cada passagem a partir da amplitude daquele ciclo específico |
| $n_i/N_i$ de um único ciclo | `dano_por_ciclo = (1.0 / ciclos_ate_falha) * self.taxa_desgaste` |
| $D = \sum n_i/N_i$ | `self._dano_acumulado`, somado a cada chamada de `registrar_passagem_de_trem` |
| $D \geq 1$ | `dano_acumulado >= LIMIAR_CRITICO` (0.7, não 1.0, de propósito: o alerta dispara antes da falha teórica, com margem de segurança) |

`taxa_desgaste` não vem da teoria clássica, é uma extensão: um multiplicador
por sensor que simula variação de qualidade do material ou da instalação
entre pontos diferentes da mesma linha. Sem ele, todo sensor teria a mesma
trajetória de dano, e não haveria nada para o motor de análise da próxima
fase aprender a distinguir.

### A ressalva honesta

O expoente escolhido (`EXPOENTE_BASQUIN = 6.0`, equivalente a $b \approx
-0.167$) é bem mais agressivo que valores típicos de metais reais ($b$
entre $-0{,}05$ e $-0{,}12$). A escolha é deliberada: com um $b$ realista, a
simulação levaria dias inteiros de tempo real para acumular dano visível.
Com o expoente atual, o dano evolui em minutos, rápido o suficiente para
testar e demonstrar o pipeline inteiro numa sessão de trabalho. $\sigma'_f$
também é um valor de exemplo, não veio de ensaio de material do cabo de
catenária real. O código também simplifica a conversão entre reversões e
ciclos ($2N_f$ na fórmula original vira $N_f$ direto), sem impacto na
lógica de acúmulo, só na escala absoluta do número.

**Isso não substitui uma análise estrutural certificada.** O número final
que o modelo cospe importa menos do que a arquitetura que o produz. O
pipeline de ingestão, processamento e decisão é o mesmo formato que um
sistema de monitoramento real usaria: sensores medem ciclos de tensão,
Basquin estima quantos ciclos aquele nível aguenta, Miner soma o dano
histórico, e um limiar dispara o alerta antes da falha. Só o material por
trás dos números que é de exemplo, não a lógica que os processa.

---

## Estado atual

| Componente | Status |
|---|---|
| Simulador de sensores | **Pronto** |
| Gateway de ingestão (Go) | Planejado |
| Motor de análise (Python) | Planejado |
| Persistência (Supabase) | Planejado |
| Dashboard (Streamlit) | Planejado |

---

## Simulador de sensores

Gera a rede inteira de pontos de sensor e produz leituras de vibração
fisicamente plausíveis, uma janela por sensor por segundo, em NDJSON
(um objeto JSON por linha), o formato que o gateway em Go vai consumir na
próxima fase.

```bash
pip install -r requirements.txt
python scripts/simular_sensores.py --resumo
```

`--resumo` mostra só a contagem de sensores por estado a cada janela, útil
para acompanhar a simulação sem o volume bruto de dados. Sem essa flag, cada
linha da saída é uma leitura completa (`src/simulador/sensor.py:LeituraSensor`),
pronta pra virar entrada de rede depois:

```bash
python scripts/simular_sensores.py --extensao-km 5 --sensores-por-km 10 --duracao-s 30
```

**O que cada sensor simula de verdade, não só ruído aleatório:**

- **Acúmulo de dano por fadiga** segue a regra de Basquin (tensão cíclica vs.
  ciclos até falha) somada pela regra de Palmgren-Miner a cada passagem de
  trem simulada. 2% dos pontos nascem com taxa de desgaste 8 a 20 vezes maior
  que o normal, simulando catenária mais antiga ou com defeito de instalação,
  o padrão que o motor de análise da próxima fase vai ter que aprender a
  distinguir olhando só o sinal de vibração.
- **O sinal de vibração muda com o dano acumulado.** A amplitude na frequência
  de ressonância estrutural (18 Hz) escala com a tensão mecânica instantânea,
  o acoplamento de 60 Hz da rede de tração está sempre presente, e o ruído de
  banda larga cresce com o dano, o efeito de folga mecânica e microfraturas
  numa catenária degradada.
- **Ciclo térmico diário** (comprimido em 5 minutos simulados) desloca a
  linha de base do sinal, a mesma variação que dilatação térmica real
  causaria ao longo de um dia.

**Testado na escala que o problema pede:** uma janela de leitura para os
2.000 sensores da configuração padrão (40km, 50 sensores/km) roda em
~165ms de CPU só para gerar os dados, antes de qualquer I/O de rede. É
esse número que torna a escolha de Go para o gateway uma decisão de
engenharia, não estética: a geração de dados sozinha já consome uma fatia
grande do orçamento de 1 segundo por janela, sobra pouco espaço para um
gargalo de concorrência na ingestão.

---

## Estrutura do projeto

```
├── cmd/gateway/                  gateway de ingestão em Go (planejado)
├── src/
│   └── simulador/
│       ├── sensor.py              modelo físico de um ponto (fadiga, vibração)
│       ├── rede.py                distribuição espacial e orquestração temporal
│       └── transporte.py          serialização NDJSON
├── scripts/
│   └── simular_sensores.py        CLI do simulador
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
