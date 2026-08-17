"""Dashboard de monitoramento preditivo de catenária.

Lê direto do Supabase via REST com a chave anon (só select, RLS garante
isso, ver `src/persistencia/leitura.py`). Não fala com o gateway nem com o
motor de análise, só consome o que eles já persistiram: é a ponta
puramente de visualização do pipeline `simulador -> gateway em Go -> motor
de análise -> Supabase -> aqui`.

O visual reusa os mesmos tokens dos outros projetos do portfólio LCML
(fundo #0a0a0b, destaque âmbar #f5a524, monoespaçada nos números), para os
três lerem como um conjunto. Os componentes padrão do Streamlit
(`st.metric`, `st.dataframe` cru) foram trocados por marcação própria:
eles denunciam a ferramenta em vez de comunicar o dado.
"""

from __future__ import annotations

import os

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.persistencia.leitura import buscar_alertas, buscar_leituras
from src.analise.aprendizado import coletar_dataset_sintetico
from src.analise.espectro import estimar_dano_espectral
from src.simulador.sensor import (
    EXPOENTE_BASQUIN,
    EXPOENTE_BASQUIN_REAL,
    LIMIAR_CRITICO as LIMIAR_CRITICO_SIM,
    TENSAO_REFERENCIA_N,
    TENSAO_REFERENCIA_REAL_N,
    PontoSensor,
)

st.set_page_config(
    page_title="Monitoramento Preditivo de Catenária",
    page_icon="⚡",
    layout="wide",
)

FUNDO = "#0a0a0b"
SUPERFICIE = "#131316"
SUPERFICIE_ALTA = "#1b1b20"
BORDA = "#292930"
TEXTO = "#f4f4f5"
TEXTO_SUAVE = "#8b8b96"
TEXTO_FRACO = "#5a5a66"
AMBAR = "#f5a524"
VERDE = "#7dd3a8"
VERMELHO = "#f2777a"
AZUL = "#7aa2f7"

COR_ESTADO = {"NORMAL": VERDE, "ATENCAO": AMBAR, "CRITICO": VERMELHO}
LIMIAR_ATENCAO = 0.3
LIMIAR_CRITICO = 0.7

ESTILO = f"""
<style>
:root {{
    --fundo: {FUNDO}; --superficie: {SUPERFICIE}; --superficie-alta: {SUPERFICIE_ALTA};
    --borda: {BORDA}; --texto: {TEXTO}; --texto-suave: {TEXTO_SUAVE};
    --texto-fraco: {TEXTO_FRACO}; --destaque: {AMBAR}; --verde: {VERDE};
    --vermelho: {VERMELHO}; --azul: {AZUL};
}}

.stApp {{ background: var(--fundo); }}
#MainMenu, footer, header {{ visibility: hidden; }}
.block-container {{ padding: 2.2rem 3rem 4rem; max-width: 1280px; }}

.marca {{
    display: block; color: var(--destaque); font-size: 0.7rem; font-weight: 700;
    letter-spacing: 0.16em; text-transform: uppercase; margin-bottom: 0.7rem;
}}
h1.titulo {{
    color: var(--texto); font-size: 2.6rem; font-weight: 700;
    letter-spacing: -0.035em; line-height: 1.05; margin: 0 0 0.7rem;
}}
.chamada {{ color: var(--texto-suave); font-size: 0.97rem; line-height: 1.65; max-width: 68ch; }}
.chamada strong {{ color: var(--texto); font-weight: 600; }}

.faixa {{ display: flex; gap: 1rem; margin: 2rem 0 1.2rem; flex-wrap: wrap; }}
.cartao {{
    flex: 1; min-width: 190px; background: var(--superficie);
    border: 1px solid var(--borda); border-radius: 14px; padding: 1.1rem 1.2rem;
}}
.cartao-valor {{
    font-family: ui-monospace, "Cascadia Code", Consolas, monospace;
    font-size: 2rem; font-weight: 600; line-height: 1; color: var(--texto);
}}
.cartao-rotulo {{
    color: var(--texto-fraco); font-size: 0.68rem; text-transform: uppercase;
    letter-spacing: 0.11em; margin-top: 0.45rem; font-weight: 700;
}}
.cartao-nota {{ color: var(--texto-fraco); font-size: 0.74rem; margin-top: 0.55rem; line-height: 1.45; }}
.v-ambar {{ color: var(--destaque); }}
.v-verde {{ color: var(--verde); }}
.v-vermelho {{ color: var(--vermelho); }}
.v-azul {{ color: var(--azul); }}

.secao {{
    color: var(--texto); font-size: 1.02rem; font-weight: 700;
    letter-spacing: -0.01em; margin: 2.4rem 0 0.3rem;
}}
.secao-sub {{ color: var(--texto-fraco); font-size: 0.8rem; line-height: 1.55; margin-bottom: 1rem; max-width: 78ch; }}

.painel {{
    background: var(--superficie); border: 1px solid var(--borda);
    border-radius: 14px; padding: 1.3rem 1.4rem; margin-bottom: 0.9rem;
}}
.painel.alerta {{ border-color: rgba(245,165,36,0.45); }}

.sensor-topo {{ display: flex; align-items: baseline; gap: 0.8rem; flex-wrap: wrap; margin-bottom: 1rem; }}
.sensor-id {{
    font-family: ui-monospace, monospace; color: var(--texto);
    font-size: 1.05rem; font-weight: 700; letter-spacing: -0.01em;
}}
.sensor-km {{ color: var(--texto-fraco); font-size: 0.8rem; font-family: ui-monospace, monospace; }}
.etiqueta {{
    font-size: 0.63rem; font-weight: 700; letter-spacing: 0.1em; text-transform: uppercase;
    padding: 0.22rem 0.55rem; border-radius: 999px; border: 1px solid;
}}
.etiqueta.atencao {{ color: var(--destaque); border-color: rgba(245,165,36,0.4); background: rgba(245,165,36,0.09); }}
.etiqueta.critico {{ color: var(--vermelho); border-color: rgba(242,119,122,0.4); background: rgba(242,119,122,0.09); }}
.etiqueta.acelerado {{ color: var(--azul); border-color: rgba(122,162,247,0.4); background: rgba(122,162,247,0.09); }}

.linha-barra {{ display: flex; align-items: center; gap: 0.85rem; margin-bottom: 0.55rem; }}
.barra-nome {{ width: 12.5rem; color: var(--texto-suave); font-size: 0.79rem; }}
.barra-trilho {{
    flex: 1; height: 9px; background: var(--superficie-alta);
    border-radius: 99px; overflow: hidden; position: relative;
}}
.barra-preenchida {{ height: 100%; border-radius: 99px; }}
.marca-limiar {{ position: absolute; top: -3px; width: 1px; height: 15px; background: var(--borda); }}
.barra-valor {{
    font-family: ui-monospace, monospace; width: 3.4rem; text-align: right;
    color: var(--texto); font-size: 0.8rem;
}}

.rodape-sensor {{
    display: flex; gap: 1.8rem; flex-wrap: wrap; margin-top: 1rem;
    padding-top: 0.9rem; border-top: 1px solid var(--borda);
}}
.mini-rotulo {{ color: var(--texto-fraco); font-size: 0.64rem; text-transform: uppercase; letter-spacing: 0.1em; }}
.mini-valor {{ font-family: ui-monospace, monospace; color: var(--texto-suave); font-size: 0.88rem; margin-top: 0.2rem; }}

.passos {{ display: flex; gap: 0.9rem; flex-wrap: wrap; margin-bottom: 0.6rem; }}
.passo {{
    flex: 1; min-width: 220px; background: var(--superficie);
    border: 1px solid var(--borda); border-radius: 14px; padding: 1.1rem 1.2rem;
}}
.passo-num {{
    font-family: ui-monospace, monospace; color: var(--destaque);
    font-size: 0.72rem; font-weight: 700; letter-spacing: 0.1em; margin-bottom: 0.5rem;
}}
.passo-titulo {{ color: var(--texto); font-size: 0.92rem; font-weight: 700; margin-bottom: 0.4rem; }}
.passo-texto {{ color: var(--texto-suave); font-size: 0.82rem; line-height: 1.6; }}
.passo-texto em {{ color: var(--texto-fraco); font-style: normal; font-size: 0.76rem;
    display: block; margin-top: 0.5rem; }}

.dicionario {{ display: flex; flex-direction: column; gap: 0.9rem; }}
.verbete {{ display: grid; grid-template-columns: 13rem 1fr; gap: 1.2rem; align-items: start; }}
.verbete-termo {{ color: var(--texto); font-size: 0.83rem; font-weight: 700; }}
.verbete-termo span {{ display: block; color: var(--texto-fraco); font-weight: 400; font-size: 0.72rem; margin-top: 0.15rem; }}
.verbete-desc {{ color: var(--texto-suave); font-size: 0.83rem; line-height: 1.6; }}
.verbete-desc code {{
    background: var(--superficie-alta); color: var(--destaque);
    padding: 0.08rem 0.32rem; border-radius: 4px; font-size: 0.78rem;
}}

div[data-testid="stExpander"] {{
    border: 1px solid var(--borda); border-radius: 14px; background: var(--superficie);
}}
div[data-testid="stExpander"] summary {{ color: var(--texto-suave); font-size: 0.85rem; font-weight: 600; }}
div[data-testid="stExpander"] summary:hover {{ color: var(--destaque); }}

div[data-baseweb="select"] > div {{
    background: var(--superficie); border-color: var(--borda); border-radius: 10px;
}}
.stSelectbox label {{ color: var(--texto-fraco) !important; font-size: 0.7rem !important;
    text-transform: uppercase; letter-spacing: 0.1em; font-weight: 700 !important; }}

.vazio {{
    background: var(--superficie); border: 1px dashed var(--borda); border-radius: 14px;
    padding: 2rem; text-align: center; color: var(--texto-fraco); font-size: 0.88rem;
}}
.aviso-tempo {{
    background: rgba(122,162,247,0.07); border: 1px solid rgba(122,162,247,0.3);
    border-radius: 12px; padding: 0.85rem 1.1rem; margin-bottom: 1.6rem;
    color: var(--texto-suave); font-size: 0.8rem; line-height: 1.6;
}}
.aviso-tempo strong {{ color: var(--azul); }}
.mini-nota {{ color: var(--texto-fraco); font-size: 0.62rem; margin-top: 0.1rem; line-height: 1.3; }}

.comparativo {{ display: flex; gap: 1rem; flex-wrap: wrap; margin-bottom: 1rem; }}
.comp-cartao {{
    flex: 1; min-width: 220px; background: var(--superficie);
    border: 1px solid var(--borda); border-radius: 14px; padding: 1.1rem 1.3rem;
}}
.comp-cartao.vencedor {{ border-color: rgba(125,211,168,0.45); }}
.comp-titulo {{ color: var(--texto); font-size: 0.88rem; font-weight: 700; margin-bottom: 0.7rem; }}
.comp-valor {{
    font-family: ui-monospace, monospace; font-size: 1.7rem; font-weight: 600; color: var(--texto);
}}
.comp-rotulo {{ color: var(--texto-fraco); font-size: 0.68rem; text-transform: uppercase;
    letter-spacing: 0.09em; margin-top: 0.3rem; }}
.selo-vencedor {{
    display: inline-block; margin-top: 0.6rem; font-size: 0.65rem; font-weight: 700;
    color: var(--verde); letter-spacing: 0.08em; text-transform: uppercase;
}}
.rodape {{
    color: var(--texto-fraco); font-size: 0.72rem; line-height: 1.6;
    margin-top: 3.2rem; padding-top: 1.5rem; border-top: 1px solid var(--borda);
}}
</style>
"""


def _credenciais() -> tuple[str | None, str | None]:
    url = st.secrets.get("SUPABASE_URL", os.environ.get("SUPABASE_URL"))
    chave = st.secrets.get("SUPABASE_ANON_KEY", os.environ.get("SUPABASE_ANON_KEY"))
    return url, chave


@st.cache_data(ttl=10, show_spinner=False)
def _carregar(url: str, chave: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    leituras = pd.DataFrame(buscar_leituras(url, chave))
    alertas = pd.DataFrame(buscar_alertas(url, chave, limite=200))
    if not leituras.empty:
        leituras["lido_em"] = pd.to_datetime(leituras["lido_em"])
        leituras = leituras.sort_values("lido_em")
    if not alertas.empty:
        alertas["disparado_em"] = pd.to_datetime(alertas["disparado_em"])
    return leituras, alertas


def _cartao(valor, rotulo: str, nota: str, classe: str = "") -> str:
    return (
        f'<div class="cartao"><div class="cartao-valor {classe}">{valor}</div>'
        f'<div class="cartao-rotulo">{rotulo}</div>'
        f'<div class="cartao-nota">{nota}</div></div>'
    )


def _barra(nome: str, valor: float, cor: str) -> str:
    largura = max(0.0, min(1.0, valor)) * 100
    return (
        f'<div class="linha-barra"><div class="barra-nome">{nome}</div>'
        f'<div class="barra-trilho">'
        f'<div class="barra-preenchida" style="width:{largura:.1f}%;background:{cor};"></div>'
        f'<div class="marca-limiar" style="left:{LIMIAR_ATENCAO*100:.0f}%;"></div>'
        f'<div class="marca-limiar" style="left:{LIMIAR_CRITICO*100:.0f}%;"></div>'
        f'</div>'
        f'<div class="barra-valor">{valor:.3f}</div></div>'
    )


def _formatar_rul(segundos) -> str:
    if pd.isna(segundos):
        return "sem dado"
    if segundos < 120:
        return f"{segundos:.0f} s"
    if segundos < 7200:
        return f"{segundos/60:.0f} min"
    return f"{segundos/3600:.1f} h"


def _tema_grafico(fig: go.Figure, altura: int) -> go.Figure:
    fig.update_layout(
        height=altura,
        margin=dict(l=8, r=8, t=8, b=8),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color=TEXTO_SUAVE, size=12),
        legend=dict(orientation="h", y=1.14, x=0, bgcolor="rgba(0,0,0,0)"),
        hoverlabel=dict(bgcolor=SUPERFICIE_ALTA, bordercolor=BORDA, font_color=TEXTO),
    )
    fig.update_xaxes(gridcolor=BORDA, zeroline=False, linecolor=BORDA)
    fig.update_yaxes(gridcolor=BORDA, zeroline=False, linecolor=BORDA)
    return fig


@st.cache_data(ttl=3600, show_spinner=False)
def _comparar_ml_vs_fisico() -> dict:
    """Reproduz scripts/treinar_estimador_ml.py, cacheado por 1h (é determinístico)."""
    from src.analise.aprendizado import _rede_treinada
    import numpy as np

    reserva = np.linspace(0.03, 0.97, 12)
    rede = _rede_treinada()
    X, y, vibracoes = coletar_dataset_sintetico(reserva, seed=7)

    estimados_ml = np.clip(rede.predict(X), 0.0, 1.0)
    erro_ml = float(np.mean(np.abs(estimados_ml - y)))

    estimados_esp = np.array([estimar_dano_espectral(v) for v in vibracoes])
    erro_esp = float(np.mean(np.abs(estimados_esp - y)))

    return {"erro_ml": erro_ml, "erro_espectral": erro_esp, "amostras": len(y)}


@st.cache_data(ttl=3600, show_spinner=False)
def _comparar_regime_real() -> dict:
    """Reproduz scripts/comparar_regime_real.py, cacheado por 1h (é determinístico)."""
    import numpy as np

    def passagens_ate_critico(tensao_ref, expoente, seed, limite=2_000_000):
        rng = np.random.default_rng(seed)
        ponto = PontoSensor(sensor_id="CMP", km=0.0, tensao_base_n=13000.0, _rng=rng)
        for i in range(1, limite + 1):
            amplitude = rng.uniform(3000, 9000)
            ponto.registrar_passagem_de_trem(amplitude, tensao_ref, expoente)
            if ponto.dano_acumulado >= LIMIAR_CRITICO_SIM:
                return i
        return None

    trens_por_dia = 120
    passagens_demo = passagens_ate_critico(TENSAO_REFERENCIA_N, EXPOENTE_BASQUIN, seed=42)
    passagens_real = passagens_ate_critico(TENSAO_REFERENCIA_REAL_N, EXPOENTE_BASQUIN_REAL, seed=42)

    return {
        "passagens_demo": passagens_demo,
        "dias_demo": passagens_demo / trens_por_dia if passagens_demo else None,
        "passagens_real": passagens_real,
        "dias_real": passagens_real / trens_por_dia if passagens_real else None,
        "fator": passagens_real / passagens_demo if passagens_demo and passagens_real else None,
    }


def _cartao_sensor(linha: pd.Series) -> str:
    etiquetas = ""
    if linha["estado"] == "ATENCAO":
        etiquetas += '<span class="etiqueta atencao">atenção</span>'
    elif linha["estado"] == "CRITICO":
        etiquetas += '<span class="etiqueta critico">crítico</span>'
    if linha.get("desgaste_acelerado"):
        etiquetas += '<span class="etiqueta acelerado">desgaste acelerado</span>'

    oficial = max(linha["dano_ciclos"], linha["dano_espectral"])
    divergencia = abs(linha["dano_ciclos"] - linha.get("dano_espectral_bruto", linha["dano_espectral"]))

    return f"""
<div class="painel alerta">
  <div class="sensor-topo">
    <span class="sensor-id">{linha['sensor_id']}</span>
    <span class="sensor-km">km {linha['km']:.2f}</span>
    {etiquetas}
  </div>
  {_barra("Dano oficial (o maior)", oficial, COR_ESTADO[linha['estado']])}
  {_barra("por ciclos, Basquin/Miner", linha['dano_ciclos'], BORDA)}
  {_barra("espectral, FFT", linha['dano_espectral'], AZUL)}
  {_barra("rede neural (comparativo)", linha['dano_ml'], "#9d7cd8") if pd.notna(linha.get('dano_ml')) else ''}
  <div class="rodape-sensor">
    <div><div class="mini-rotulo">divergência</div><div class="mini-valor">{divergencia:.3f}</div></div>
    <div><div class="mini-rotulo">vida útil restante</div><div class="mini-valor">{_formatar_rul(linha['rul_segundos'])}</div><div class="mini-nota">relógio acelerado da demo</div></div>
    <div><div class="mini-rotulo">sinal/ruído</div><div class="mini-valor">{linha['snr_db']:.1f} dB</div></div>
    <div><div class="mini-rotulo">ciclos contados</div><div class="mini-valor">{int(linha['ciclos_contados'])}</div></div>
  </div>
</div>
"""


PASSOS = [
    (
        "Os sensores medem",
        "Cada ponto da via manda, a cada segundo, o quanto o cabo está vibrando e a força que "
        "ele está aguentando. Vibração importa porque um cabo desgastado treme diferente de um "
        "cabo novo, do mesmo jeito que uma peça solta chacoalha.",
        "150 pontos simulados nesta demonstração",
    ),
    (
        "Tudo chega junto",
        "Milhares de sensores falando ao mesmo tempo viram um problema de trânsito de dados. "
        "Um programa em Go recebe todas as conexões em paralelo e organiza as leituras sem "
        "perder nenhuma, mesmo em pico.",
        "testado com 2.000 sensores simultâneos, zero falhas",
    ),
    (
        "O sistema calcula o desgaste",
        "Duas contas independentes rodam sobre os mesmos dados: uma soma o estrago de cada trem "
        "que passou, outra escuta o ruído da vibração. Quando as duas discordam muito, é sinal "
        "de que aquele ponto tem algo errado além do uso normal.",
        "erro médio de 0,4% contra o desgaste real",
    ),
    (
        "O painel mostra o risco",
        "Cada ponto recebe um estado: normal, atenção ou crítico. Quem está em atenção aparece "
        "no topo com a estimativa de quanto tempo falta, para a equipe priorizar a viagem até "
        "lá antes que o cabo arrebente.",
        "é o que você está vendo abaixo",
    ),
]

DICIONARIO = [
    (
        "Dano acumulado", "de 0 a 1",
        "Quanto da vida do cabo já foi gasta. <code>0</code> é cabo novo, <code>1</code> seria o "
        "rompimento. O alerta não espera chegar em 1: a partir de <code>0.3</code> o ponto entra "
        "em atenção e em <code>0.7</code> vira crítico, para sobrar tempo de ir lá trocar.",
    ),
    (
        "Por ciclos", "conta o que o trem faz",
        "Soma o estrago de cada trem que passou, do mesmo jeito que dobrar um arame muitas vezes "
        "acaba quebrando ele. Funciona bem para uso normal, mas <strong>não enxerga defeito de "
        "fábrica ou instalação</strong>: dois pontos que aguentaram os mesmos trens dão a mesma "
        "conta, mesmo que um deles esteja bem pior que o outro.",
    ),
    (
        "Espectral", "escuta a vibração",
        "Olha o chiado do sinal de vibração. O cabo tem duas vibrações que sempre existem e são "
        "conhecidas (a do próprio cabo balançando e a da rede elétrica), então o sistema separa "
        "essas duas e mede o resto. Esse resto cresce quando aparecem microtrincas e folga, "
        "então <strong>denuncia o estado real do cabo</strong>, não importa quantos trens passaram.",
    ),
    (
        "Dano oficial", "vale o pior dos dois",
        "Entre as duas contas, o sistema fica sempre com a mais pessimista. Num sistema feito "
        "para avisar antes da falha, escolher o número menor seria justamente ignorar o aviso "
        "que importa.",
    ),
    (
        "Divergência", "as duas contas discordando",
        "A diferença entre as duas contas. Se o trem que passou não explica o estrago que a "
        "vibração mostra, tem algo errado com aquele ponto específico: cabo velho, emenda ruim, "
        "instalação malfeita. Acima de <code>0.15</code> o ponto é marcado, e isso aparece "
        "<strong>antes</strong> mesmo dele virar caso de atenção.",
    ),
    (
        "Vida útil restante", "quanto tempo falta",
        "Olhando o ritmo em que aquele ponto vem se desgastando, quanto tempo até chegar no "
        "nível crítico. Serve para decidir a ordem das visitas da equipe, não como data marcada: "
        "se o ritmo mudar, a estimativa muda junto. <strong>Nesta demonstração o relógio é "
        "acelerado</strong> (ver aviso no topo do painel), então os minutos aqui equivalem a "
        "semanas ou meses reais, não é a via se desgastando de verdade tão rápido.",
    ),
    (
        "Sinal/ruído", "qualidade da leitura",
        "O quanto o sinal limpo se destaca do chiado. Cai conforme o cabo piora, porque é o "
        "chiado que aumenta. Também serve para saber se dá para confiar na medição, já que via "
        "eletrificada tem muita interferência.",
    ),
]


def main() -> None:
    st.markdown(ESTILO, unsafe_allow_html=True)

    st.markdown('<span class="marca">LCML · Manutenção preditiva ferroviária</span>', unsafe_allow_html=True)
    st.markdown('<h1 class="titulo">Monitoramento de catenária</h1>', unsafe_allow_html=True)
    st.markdown(
        '<p class="chamada">A <strong>catenária</strong> é o cabo suspenso acima dos trilhos que '
        'leva energia até o trem. Ela trabalha o tempo todo sob esforço: o peso de cada composição '
        'que passa, vento, o calor que dilata o cabo, o atrito do pantógrafo. Esse desgaste se '
        'acumula em silêncio durante meses, e quando o cabo rompe, ele rompe sem aviso, deixando '
        'a linha parada.</p>'
        '<p class="chamada" style="margin-top:0.9rem;">Este projeto espalha <strong>sensores ao '
        'longo da via</strong> para medir a vibração e o esforço em cada ponto, e calcula quanto '
        'da vida útil cada trecho já gastou. O objetivo é direto: <strong>apontar quais pontos vão '
        'falhar primeiro</strong>, para a manutenção chegar antes do rompimento em vez de correr '
        'atrás depois.</p>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="aviso-tempo"><strong>Relógio acelerado.</strong> Esta é uma demonstração: '
        'o simulador comprime meses de desgaste real em minutos, para o pipeline inteiro poder '
        'ser testado numa sessão de trabalho em vez de esperar dias. Os valores de "vida útil '
        'restante" abaixo seguem esse mesmo relógio acelerado, então não leia os minutos como '
        'minutos reais de via, o que importa é a ordem de prioridade entre os pontos.</div>',
        unsafe_allow_html=True,
    )

    url, chave = _credenciais()
    if not url or not chave:
        st.markdown(
            '<div class="vazio">Faltam credenciais do Supabase. Copie '
            '<code>.streamlit/secrets.toml.example</code> para <code>.streamlit/secrets.toml</code>.</div>',
            unsafe_allow_html=True,
        )
        st.stop()

    try:
        leituras, alertas = _carregar(url, chave)
    except Exception as erro:
        st.markdown(f'<div class="vazio">Falha ao consultar o Supabase: {erro}</div>', unsafe_allow_html=True)
        st.stop()

    if leituras.empty:
        st.markdown(
            '<div class="vazio">Nenhuma leitura no banco ainda.<br>Rode '
            '<code>python scripts/motor_analise.py --arquivo leituras.ndjson --supabase</code>.</div>',
            unsafe_allow_html=True,
        )
        st.stop()

    ultimo = leituras.sort_values("lido_em").groupby("sensor_id").tail(1)
    em_atencao = int((ultimo["estado"] == "ATENCAO").sum())
    criticos = int((ultimo["estado"] == "CRITICO").sum())
    acelerados = sorted(leituras.loc[leituras.get("desgaste_acelerado", False) == True, "sensor_id"].unique())

    st.markdown(
        '<div class="faixa">'
        + _cartao(len(ultimo), "Sensores na linha", "Um ponto de medição a cada trecho da via.")
        + _cartao(em_atencao, "Em atenção", f"Dano acima de {LIMIAR_ATENCAO}, ainda com margem.",
                  "v-ambar" if em_atencao else "")
        + _cartao(criticos, "Em estado crítico", f"Dano acima de {LIMIAR_CRITICO}, intervenção prioritária.",
                  "v-vermelho" if criticos else "v-verde")
        + _cartao(len(acelerados), "Desgaste acelerado",
                  "Degradam mais rápido do que a carga explica. Aviso antecipado.",
                  "v-azul" if acelerados else "")
        + "</div>",
        unsafe_allow_html=True,
    )

    st.markdown('<div class="secao">Como funciona</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="secao-sub">Do cabo na via até o alerta na tela, em quatro etapas.</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="passos">'
        + "".join(
            f'<div class="passo"><div class="passo-num">{i:02d}</div>'
            f'<div class="passo-titulo">{titulo}</div>'
            f'<div class="passo-texto">{texto}<em>{nota}</em></div></div>'
            for i, (titulo, texto, nota) in enumerate(PASSOS, start=1)
        )
        + "</div>",
        unsafe_allow_html=True,
    )

    with st.expander("Como ler este painel, e o que cada número significa"):
        verbetes = "".join(
            f'<div class="verbete"><div class="verbete-termo">{termo}<span>{sub}</span></div>'
            f'<div class="verbete-desc">{desc}</div></div>'
            for termo, sub, desc in DICIONARIO
        )
        st.markdown(f'<div class="dicionario">{verbetes}</div>', unsafe_allow_html=True)

    st.markdown('<div class="secao">Pontos que exigem atenção</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="secao-sub">As três barras mostram o mesmo sensor visto de três formas. '
        'Os traços verticais nas barras marcam os limiares de atenção e crítico. Quando a barra '
        'espectral (azul) fica bem acima da de ciclos (cinza), é desgaste acelerado: o cabo se '
        'degrada mais rápido do que a carga sozinha explicaria.</div>',
        unsafe_allow_html=True,
    )

    risco = ultimo[(ultimo["estado"] != "NORMAL") | (ultimo["sensor_id"].isin(acelerados))]
    risco = risco.assign(_ordem=risco[["dano_ciclos", "dano_espectral"]].max(axis=1)).sort_values(
        "_ordem", ascending=False
    )

    if risco.empty:
        st.markdown('<div class="vazio">Nenhum ponto em risco no momento.</div>', unsafe_allow_html=True)
    else:
        for _, linha in risco.iterrows():
            st.markdown(_cartao_sensor(linha), unsafe_allow_html=True)

    st.markdown('<div class="secao">A linha inteira, quilômetro a quilômetro</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="secao-sub">Cada ponto é um sensor na sua posição real da via. A altura é o '
        'dano oficial. As faixas horizontais marcam onde começa a atenção e o estado crítico.</div>',
        unsafe_allow_html=True,
    )

    mapa = ultimo.assign(dano=ultimo[["dano_ciclos", "dano_espectral"]].max(axis=1))
    fig = go.Figure()
    fig.add_hrect(y0=LIMIAR_ATENCAO, y1=LIMIAR_CRITICO, fillcolor=AMBAR, opacity=0.05, line_width=0)
    fig.add_hrect(y0=LIMIAR_CRITICO, y1=1.0, fillcolor=VERMELHO, opacity=0.06, line_width=0)
    for estado in ("NORMAL", "ATENCAO", "CRITICO"):
        g = mapa[mapa["estado"] == estado]
        if g.empty:
            continue
        fig.add_trace(go.Scatter(
            x=g["km"], y=g["dano"], mode="markers", name=estado.lower(),
            marker=dict(size=9, color=COR_ESTADO[estado], line=dict(width=1, color=FUNDO)),
            customdata=g[["sensor_id", "dano_ciclos", "dano_espectral"]],
            hovertemplate="<b>%{customdata[0]}</b><br>km %{x:.2f}<br>"
                          "ciclos %{customdata[1]:.3f} · espectral %{customdata[2]:.3f}<extra></extra>",
        ))
    fig.update_xaxes(title_text="posição na linha (km)")
    fig.update_yaxes(title_text="dano oficial", range=[-0.03, 1.0])
    st.plotly_chart(_tema_grafico(fig, 340), use_container_width=True, config={"displayModeBar": False})

    st.markdown('<div class="secao">Um sensor ao longo do tempo</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="secao-sub">Nos pontos saudáveis as duas curvas andam juntas. Quando elas se '
        'separam, o ponto está se degradando por algo que a contagem de ciclos não vê. Escolha um '
        'dos sensores marcados como desgaste acelerado para ver o efeito.</div>',
        unsafe_allow_html=True,
    )

    sensores = sorted(leituras["sensor_id"].unique())
    padrao = sensores.index(acelerados[0]) if acelerados else 0
    escolhido = st.selectbox("Sensor", sensores, index=padrao)
    hist = leituras[leituras["sensor_id"] == escolhido]

    fig2 = go.Figure()
    fig2.add_hline(y=LIMIAR_ATENCAO, line=dict(color=AMBAR, width=1, dash="dot"),
                   annotation_text="atenção", annotation_font_color=TEXTO_FRACO)
    fig2.add_trace(go.Scatter(x=hist["lido_em"], y=hist["dano_ciclos"], name="por ciclos",
                              mode="lines", line=dict(color=TEXTO_FRACO, width=2)))
    fig2.add_trace(go.Scatter(x=hist["lido_em"], y=hist["dano_espectral"], name="espectral",
                              mode="lines", line=dict(color=AZUL, width=2)))
    if "dano_ml" in hist and hist["dano_ml"].notna().any():
        fig2.add_trace(go.Scatter(x=hist["lido_em"], y=hist["dano_ml"], name="rede neural",
                                  mode="lines", line=dict(color="#9d7cd8", width=1.5, dash="dot")))
    fig2.update_yaxes(title_text="dano estimado")
    st.plotly_chart(_tema_grafico(fig2, 300), use_container_width=True, config={"displayModeBar": False})

    st.markdown('<div class="secao">Rede neural vs. estimador físico</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="secao-sub">Treinei uma rede neural pequena no mesmo simulador e com a mesma '
        'verdade usados para medir o estimador espectral, e medi as duas num conjunto de dano nunca '
        'visto no treino. Não é sorte de uma rodada: testado em 4 pares de sementes diferentes, o '
        'físico venceu as 4 (detalhe no README).</div>',
        unsafe_allow_html=True,
    )
    try:
        comp_ml = _comparar_ml_vs_fisico()
        venceu_espectral = comp_ml["erro_espectral"] < comp_ml["erro_ml"]
        st.markdown(
            '<div class="comparativo">'
            + f'<div class="comp-cartao{" vencedor" if venceu_espectral else ""}">'
              f'<div class="comp-titulo">Espectral (1 parâmetro calibrado)</div>'
              f'<div class="comp-valor">{comp_ml["erro_espectral"]:.4f}</div>'
              f'<div class="comp-rotulo">erro médio absoluto</div>'
              + ('<div class="selo-vencedor">venceu</div>' if venceu_espectral else '') + '</div>'
            + f'<div class="comp-cartao{"" if venceu_espectral else " vencedor"}">'
              f'<div class="comp-titulo">Rede neural (MLP, aprendida)</div>'
              f'<div class="comp-valor">{comp_ml["erro_ml"]:.4f}</div>'
              f'<div class="comp-rotulo">erro médio absoluto, {comp_ml["amostras"]} amostras de reserva</div>'
              + ('' if venceu_espectral else '<div class="selo-vencedor">venceu</div>') + '</div>'
            + '</div>',
            unsafe_allow_html=True,
        )
        st.markdown(
            '<div class="secao-sub" style="margin-top:-0.4rem;">A rede compete em desvantagem aqui: '
            'ela tem que aprender do zero, com poucas amostras, uma relação física que o estimador '
            'espectral já embute (só duas frequências do sinal carregam ruído útil). Não significa '
            'que rede neural é sempre pior, significa que, quando o modelo físico é bom e o dado é '
            'escasso, ele ainda ganha.</div>',
            unsafe_allow_html=True,
        )
    except ImportError:
        st.markdown('<div class="vazio">Precisa de scikit-learn instalado para essa comparação.</div>', unsafe_allow_html=True)

    st.markdown('<div class="secao">Regime acelerado vs. regime real</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="secao-sub">A mesma física (Basquin/Miner), rodada duas vezes: com as constantes '
        'aceleradas desta demo, e com números reais publicados (tensão de fio de contato 15-30kN por '
        'classe de velocidade, expoente de Basquin entre -0.05 e -0.12 para metais). Mede quantas '
        'passagens de trem cada regime leva até o limiar crítico.</div>',
        unsafe_allow_html=True,
    )
    comp_regime = _comparar_regime_real()
    st.markdown(
        '<div class="comparativo">'
        + '<div class="comp-cartao">'
          f'<div class="comp-titulo">Regime acelerado (esta demo)</div>'
          f'<div class="comp-valor">{comp_regime["passagens_demo"]:,}'.replace(",", ".") + '</div>'
          f'<div class="comp-rotulo">passagens até o limiar crítico · {comp_regime["dias_demo"]:.1f} dias a 120 trens/dia</div>'
          '</div>'
        + '<div class="comp-cartao vencedor">'
          f'<div class="comp-titulo">Regime real (constantes citadas)</div>'
          f'<div class="comp-valor">{comp_regime["passagens_real"]:,}'.replace(",", ".") + '</div>'
          f'<div class="comp-rotulo">passagens até o limiar crítico · {comp_regime["dias_real"]:.0f} dias '
          f'(~{comp_regime["dias_real"]/365:.2f} anos) a 120 trens/dia</div>'
          '</div>'
        + '</div>',
        unsafe_allow_html=True,
    )
    if comp_regime["fator"]:
        st.markdown(
            f'<div class="secao-sub" style="margin-top:-0.4rem;">Fator de aceleração: '
            f'<strong style="color:var(--texto);">{comp_regime["fator"]:.0f}x</strong>. O regime real '
            f'cai na ordem de grandeza certa de fadiga de infraestrutura ferroviária de verdade '
            f'(meses a anos, não minutos), o que dá mais confiança na física do modelo mesmo com '
            f'parâmetro de exemplo.</div>',
            unsafe_allow_html=True,
        )

    total = f"{len(leituras):,}".replace(",", ".")
    st.markdown(
        f'<div class="rodape">{total} leituras de {len(ultimo)} sensores · '
        f'{len(alertas)} alertas registrados · atualiza a cada 10 s<br>'
        'Pipeline: simulador em Python → gateway concorrente em Go → motor de análise → '
        'Supabase → este painel.</div>',
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
