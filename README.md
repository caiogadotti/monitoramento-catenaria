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
│   Gateway de Ingestão │  Go, uma goroutine por conexão de sensor,
│         (Go)          │  agregação concorrente via channels
└───────────┬───────────┘
            │  lotes agregados
            ▼
┌───────────────────────┐
│   Motor de Análise    │  Python, FFT do sinal de vibração,
│      (Python)         │  modelo de acúmulo de fadiga (regra de Basquin
│                       │  simplificada), classificação de risco
└───────────┬───────────┘
            │  leituras + alertas
            ▼
┌───────────────────────┐
│      Supabase         │  Postgres, histórico de leituras,
│    (Postgres)         │  alertas, pontos de sensor cadastrados
└───────────┬───────────┘
            │
            ▼
┌───────────────────────┐
│      Dashboard        │  Streamlit, mapa da linha, ranking de
│      (Streamlit)      │  pontos críticos, série temporal de vibração
└───────────────────────┘
```

| Camada | Linguagem | Por que essa escolha |
|---|---|---|
| Gateway de ingestão | **Go** | Milhares de sensores publicando simultaneamente é um problema de concorrência, não de cálculo. Goroutines lidam com milhares de conexões simultâneas com uma fração do custo de memória de threads tradicionais, e channels dão um jeito seguro de agregar leituras de múltiplas goroutines sem lock manual espalhado pelo código. Se esse gateway fosse escrito em Python, o GIL viraria gargalo exatamente na hora que mais importa: pico de tráfego. |
| Motor de análise | **Python** (NumPy, SciPy) | Análise espectral de vibração e o modelo de fadiga são contas, não I/O concorrente. É onde a densidade matemática das bibliotecas científicas do Python compensa, sem o overhead de escrever álgebra linear à mão em Go. |
| Persistência | **Supabase** (Postgres) | Mesma stack que já uso em produção. Histórico de leituras vira uma tabela simples, alertas outra, com relação direta entre elas. |
| Visualização | **Streamlit** | Prototipagem rápida de dashboard sem escrever frontend à mão, mesma escolha dos outros dois projetos deste portfólio. |

---

## O gateway, testado sob carga

`go build ./... && go vet ./...` passam limpos, mas isso só prova que o
código compila, não que a arquitetura de concorrência aguenta o que o
README promete. Por isso o projeto inclui `cmd/gerador_carga`, uma
ferramenta que abre milhares de conexões TCP reais contra o gateway e mede
o resultado, em vez de só declarar um número.

```bash
go run ./cmd/gateway --porta :9000
go run ./cmd/gerador_carga --sensores 2000 --alvo 127.0.0.1:9000 --duracao 10s
```

**Resultado medido:** 2.000 sensores simulados, conectados concorrentemente,
enviando uma leitura por segundo cada. Zero falhas de conexão, 16.000
leituras entregues, pico de 2.000 conexões TCP simultaneamente ativas no
gateway ao mesmo tempo, confirmado pelo próprio log de estatísticas do
servidor.

### Dois problemas reais que o teste de carga revelou

A primeira versão do teste de carga não passava disso: falhava em 1.381 das
2.000 conexões. O gateway em si nunca foi o problema, os dois bugs estavam
no gerador de carga:

**1. `localhost` resolve para IPv6 primeiro no Windows.** A resolução de
nome preferia `::1`, e boa parte das tentativas de conexão levava
"connection actively refused" mesmo com o gateway rodando normalmente.
Corrigido usando `127.0.0.1` explícito em vez de `localhost`.

**2. Disparar 2.000 dials no mesmo instante estoura o backlog de conexões
pendentes do sistema operacional.** Isso não é um limite do gateway (as
goroutines dão conta), é o stack TCP local recebendo SYNs mais rápido do
que consegue enfileirar. A correção não foi só técnica, foi também mais
realista: sensores de verdade também não conectam todos no mesmo
microssegundo. `cmd/gerador_carga` agora espalha a abertura das conexões
numa janela configurável (`--janela-conexao`, padrão 3s) e tenta reconectar
com um pequeno backoff antes de desistir, o mesmo comportamento que um
sensor real teria depois de um SYN perdido.

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
| $b$ (na forma $N_f = (\sigma_a/\sigma'_f)^{1/b}$) | `EXPOENTE_BASQUIN`, com $1/b = -\text{EXPOENTE}\_\text{BASQUIN}$ |
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

Numa versão certificada, os valores ilustrativos daqui viriam de normas
técnicas específicas, não de escolha livre: a ABNT NBR 8800 traz a
verificação de fadiga e as tabelas de ciclos admissíveis para estruturas
de aço; a NBR 5422 rege o cálculo mecânico de cabos aéreos suspensos sob
vento, gelo e temperatura; e a NBR 13982 especifica o próprio ensaio de
vibração eólica em cabos que gera $b$ e $\sigma'_f$ em laboratório, os
dois parâmetros que este projeto assume por exemplo. Para catenária
ferroviária especificamente, o setor no Brasil usa o manual da AREMA
junto com a NBR 8800, já que não existe uma NBR dedicada a esse caso.

---

## O motor de análise

O motor recebe o que o gateway publica (uma leitura por linha, o mesmo
schema NDJSON do simulador) e decide o risco de cada sensor de duas
formas independentes, sem nunca ler o `dano_acumulado` que o simulador já
sabe:

**1. Por ciclos (Basquin/Miner), replicado a partir da tensão bruta.**
`src/analise/fadiga.py` reimplementa a mesma regra do simulador, mas sem
conhecer a tensão de repouso do cabo de antemão, porque nenhum sensor
real conheceria. A linha de base é estimada online: leituras próximas do
valor recente atualizam a linha de base devagar, saltos abruptos acima de
1500N contam como ciclo de passagem e alimentam Basquin.

**2. Por análise espectral (FFT), a partir da vibração bruta.** O sinal
de vibração soma uma oscilação estrutural marcada, o acoplamento de 60Hz
da rede de tração, e ruído de banda larga cuja intensidade cresce com o
desgaste. `src/analise/espectro.py` separa os dois picos conhecidos do
resto do espectro via `numpy.fft.rfft`, e usa a potência que sobra (o
piso de ruído) como indício independente de dano.

### Um erro de modelo real, encontrado testando no pipeline de verdade

A primeira versão do estimador espectral parecia funcionar: calibrada e
validada isolando tensão de base e temperatura fixas, o erro médio ficava
em 0.06. Rodando no pipeline completo, com tensão de base e temperatura
variando por sensor como a rede real produz, o erro saltou para 0.13,
praticamente constante não importa o dano real, sinal de viés sistemático,
não de ruído.

A causa: o modelo original ajustava uma **reta** entre potência espectral
e dano. Fisicamente errado. Potência é o quadrado de uma amplitude, e é o
**desvio padrão** do ruído que cresce linear com o dano
(`intensidade_ruido = RUIDO_BASE + RUIDO_POR_DANO · dano`, a mesma fórmula
que gera o sinal no simulador). Uma reta ajustada numa relação quadrática
funciona por acaso na faixa estreita onde foi calibrada e falha fora dela,
e extrapolava para potência negativa perto de dano zero, o que já era o
sinal de alerta que passou despercebido na primeira validação.

A correção: `scripts/calibrar_espectro.py` agora ajusta um único fator de
escala `k` tal que `piso_de_potencia ≈ k · intensidade_ruido²`, com
tensão de base e temperatura variando junto com o dano nos dados de
calibração. `k` fica em **1.0127**, perto de 1.0, confirmando que a
potência média por bin de ruído branco é aproximadamente igual à
variância do processo no tempo. Não é um número mágico ajustado até
funcionar, é a confirmação de que a forma quadrática é a física certa.

**Resultado, no mesmo pipeline completo que antes media 0.13 de erro:**

| Estimador | Erro médio absoluto | Fonte |
|---|---:|---|
| Por ciclos (Basquin/Miner) | **0.0018** | tensão mecânica bruta |
| Espectral (FFT), modelo corrigido | **0.0021** | vibração bruta |
| Espectral (FFT), modelo original (linear) | 0.13 | mesmo dado, fórmula errada |

Testado com o pipeline real inteiro: `simulador → TCP → gateway em Go →
pipe → motor de análise`, não com dado sintético isolado.

```bash
go build -o gateway.exe ./cmd/gateway
./gateway.exe --porta :9000 | python scripts/motor_analise.py &
python scripts/simular_sensores.py --gateway 127.0.0.1:9000 --duracao-s 30
```

### RUL e SNR: duas métricas a mais, sem inventar sensor novo

Além do dano bruto, o motor calcula duas métricas comuns em manutenção
preditiva de verdade, reaproveitando o que já é computado a cada leitura:

**Vida útil restante (RUL).** `AcumuladorDano` (`src/analise/fadiga.py`)
agora recebe o timestamp de cada leitura e extrapola linearmente a taxa
média de acúmulo de dano desde a primeira leitura daquele sensor para
estimar quanto tempo falta até cruzar `LIMIAR_CRITICO`. É uma
extrapolação simples, não uma regressão robusta a mudança de regime, e o
código documenta essa limitação explicitamente: ela assume que o ritmo de
desgaste observado até agora continua igual.

**SNR (relação sinal-ruído).** O motor já separa os dois picos conhecidos
do espectro (18Hz estrutural, 60Hz da rede) do resto para calcular o dano
espectral. O SNR (`src/analise/espectro.py:estimar_snr_db`) é a mesma
separação lida do outro lado: potência dos picos sobre potência do piso
de ruído, em dB. Serve como indicador independente de qualidade do sinal,
relevante numa via eletrificada com interferência eletromagnética alta.

**Validado com um sensor sintético de desgaste acelerado**
(`taxa_desgaste=12`, para cruzar o limiar em minutos em vez de dias):

| Métrica | Resultado medido |
|---|---|
| RUL: previsão feita a 80% do limiar crítico vs. instante real em que o cruzou | erro de 17.9s, **8.7%** do horizonte previsto |
| SNR com dano < 0.1 | **31.1 dB** |
| SNR com dano > 0.5 | **10.1 dB** |

O SNR caindo de 31dB para 10dB conforme o dano sobe confirma o que o
estimador espectral já assume: ruído de banda larga cresce com o
desgaste, então a relação sinal-ruído tem que cair. O erro do RUL em
torno de 9% é esperado de uma extrapolação linear simples, ele tende a
melhorar conforme mais leituras entram na média e piorar se o sensor
mudar de regime de desgaste de repente, o tipo de caso que uma versão
futura resolveria com regressão numa janela deslizante em vez da média
completa.

### Persistência no Supabase

Cada leitura processada e cada transição de estado (NORMAL → ATENCAO ou
CRITICO) são gravadas em duas tabelas Postgres via
`src/persistencia/supabase.py`, sem nenhuma credencial hardcoded: a
conexão inteira vem de `SUPABASE_DB_URL` no ambiente, lida em
`_url_conexao()`, que falha cedo com uma mensagem clara se a variável não
existir em vez de tentar um valor padrão.

```sql
catenaria_leituras   -- uma linha por leitura: sensor, km, tensão, temperatura,
                      -- dano_ciclos, dano_espectral, snr_db, rul_segundos, estado
catenaria_alertas    -- uma linha por transição de estado disparada
```

`scripts/motor_analise.py --supabase` acumula leituras em memória e grava
em lote (`--lote-supabase`, 50 por padrão) via
`psycopg2.extras.execute_values`, gravar linha por linha desperdiçaria a
maior parte do tempo em round-trip de rede em vez de I/O de disco. Alertas
são raros por natureza (só disparam em transição de estado), então esses
gravam imediatamente, sem esperar o lote.

**Decisão de isolamento:** o projeto Supabase da conta já tinha os dois
projetos gratuitos no limite (o banco de produção do App Corte/Estoque da
Descartee e o do Portal RH), então as tabelas deste projeto entraram
prefixadas `catenaria_` dentro do projeto `portalrh` em vez de um projeto
novo, com Row Level Security habilitada e uma policy de leitura pública
(`select` para `anon`/`authenticated`), sem policy de escrita: quem
escreve é o motor de análise, direto pela connection string, que não
passa pelo RLS de cliente.

```bash
cp .env.example .env   # preencher SUPABASE_DB_URL com a connection string do pooler
python scripts/motor_analise.py --arquivo leituras.ndjson --supabase
```

### Dashboard em Streamlit

`app.py` é a ponta puramente de visualização: não fala com o gateway nem
com o motor de análise, só lê o que já está persistido no Supabase, via
API REST com a chave anon (`src/persistencia/leitura.py`), não a
connection string do Postgres. É uma separação de privilégio deliberada:
a chave anon só consegue `select` nas duas tabelas (a policy de RLS não
inclui insert/update/delete), então mesmo exposta no cliente Streamlit
ela não é capaz de escrever nada no banco.

Mostra, por sensor e por posição na linha (km): dano por ciclos e dano
espectral lado a lado, SNR, RUL, estado atual, e o histórico de alertas
disparados. Cache de 10s (`st.cache_data`) evita bater no banco a cada
interação do usuário sem deixar o painel travado num snapshot antigo.

```bash
cp .streamlit/secrets.toml.example .streamlit/secrets.toml   # já vem preenchido, ver nota abaixo
streamlit run app.py
```

**Por que a chave anon já vem preenchida no `.example`, ao contrário da
connection string do Postgres:** chave anon do Supabase é desenhada pra
ser pública, o mesmo padrão de uma API key de Firebase em app cliente. A
segurança não vem de esconder a chave, vem da política de RLS por trás
dela. Testado localmente antes de documentar: subiu o dashboard, inseriu
leituras sintéticas direto no banco (25 sensores, estados variados),
confirmou os quatro KPIs, o mapa de dispersão por km, o gráfico de pizza
por estado, a tabela de sensores em risco e o histórico por sensor
renderizando com dado real antes de apagar o teste.

---

## Estado atual

| Componente | Status |
|---|---|
| Simulador de sensores | **Pronto** |
| Gateway de ingestão (Go) | **Pronto** |
| Motor de análise (Python) | **Pronto** |
| Persistência (Supabase) | **Pronto** |
| Dashboard (Streamlit) | **Pronto** |

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
├── cmd/
│   ├── gateway/                   gateway de ingestão TCP em Go
│   └── gerador_carga/             ferramenta de load test do gateway
├── internal/ingestao/             servidor TCP concorrente, agregação em lotes
├── src/
│   ├── simulador/
│   │   ├── sensor.py              modelo físico de um ponto (fadiga, vibração)
│   │   ├── rede.py                distribuição espacial e orquestração temporal
│   │   └── transporte.py          serialização NDJSON, conexão com o gateway
│   ├── analise/
│   │   ├── fadiga.py              acumulador de dano por ciclos (Basquin/Miner) + RUL
│   │   ├── espectro.py            estimador de dano espectral (FFT) + SNR
│   │   └── motor.py               orquestra os dois estimadores por sensor
│   └── persistencia/
│       ├── supabase.py            grava leituras e alertas no Postgres
│       └── leitura.py             lê do Supabase via REST (chave anon, só select)
├── scripts/
│   ├── simular_sensores.py        CLI do simulador
│   ├── motor_analise.py           CLI do motor de análise
│   └── calibrar_espectro.py       calibração do estimador espectral
├── app.py                         dashboard Streamlit
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
