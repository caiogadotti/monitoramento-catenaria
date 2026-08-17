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
  <div class="rodape-sensor">
    <div><div class="mini-rotulo">divergência</div><div class="mini-valor">{divergencia:.3f}</div></div>
    <div><div class="mini-rotulo">vida útil restante</div><div class="mini-valor">{_formatar_rul(linha['rul_segundos'])}</div></div>
    <div><div class="mini-rotulo">sinal/ruído</div><div class="mini-valor">{linha['snr_db']:.1f} dB</div></div>
    <div><div class="mini-rotulo">ciclos contados</div><div class="mini-valor">{int(linha['ciclos_contados'])}</div></div>
  </div>
</div>
"""


DICIONARIO = [
    (
        "Dano acumulado", "0 a 1",
        "Fração da vida à fadiga já consumida pelo cabo, pela regra de Palmgren-Miner. "
        "<code>0</code> é cabo novo, <code>1</code> é a falha teórica. O alerta dispara "
        "antes: <code>0.3</code> vira atenção e <code>0.7</code> vira crítico, com margem de segurança.",
    ),
    (
        "Por ciclos", "Basquin/Miner",
        "Conta os picos de tensão de cada passagem de trem e soma o quanto cada ciclo consome "
        "da vida do cabo. Enxerga bem carga, mas é <strong>cego para desgaste acelerado</strong>: "
        "dois pontos com a mesma carga dão a mesma contagem, mesmo que um esteja se degradando "
        "muito mais rápido por defeito de instalação.",
    ),
    (
        "Espectral", "FFT da vibração",
        "Separa por FFT os dois picos conhecidos do sinal (18 Hz da ressonância do cabo, 60 Hz "
        "da rede de tração) e mede o ruído de banda larga que sobra. Esse ruído cresce com "
        "microfraturas e folga mecânica, então <strong>enxerga o desgaste real</strong>, "
        "independente da carga.",
    ),
    (
        "Dano oficial", "o maior dos dois",
        "O estado do sensor sai do maior valor entre os dois estimadores. É a leitura "
        "conservadora: num sistema que existe para avisar antes da falha, ignorar o estimador "
        "que está mais alto seria deixar passar justamente o caso perigoso.",
    ),
    (
        "Divergência", "desgaste acelerado",
        "Distância entre os dois estimadores. Quando passa de <code>0.15</code>, é assinatura de "
        "ponto que se degrada mais rápido que a carga explica, ou seja catenária velha ou "
        "defeituosa. Serve de aviso antecipado, antes mesmo do dano cruzar o limiar de atenção.",
    ),
    (
        "Vida útil restante", "RUL",
        "Extrapola a taxa média de acúmulo de dano do sensor para estimar quanto falta até o "
        "limiar crítico. Assume que o ritmo observado continua, então serve para priorizar "
        "manutenção, não como data de validade.",
    ),
    (
        "Sinal/ruído", "SNR, em dB",
        "Potência dos dois picos conhecidos dividida pelo piso de ruído. Cai conforme o cabo se "
        "degrada, porque é o ruído que cresce. Vale como indicador independente de qualidade do "
        "sinal, útil numa via eletrificada onde a interferência é alta.",
    ),
]


def main() -> None:
    st.markdown(ESTILO, unsafe_allow_html=True)

    st.markdown('<span class="marca">LCML · Manutenção preditiva ferroviária</span>', unsafe_allow_html=True)
    st.markdown('<h1 class="titulo">Monitoramento de catenária</h1>', unsafe_allow_html=True)
    st.markdown(
        '<p class="chamada">Sensores simulados ao longo da linha publicam vibração e tensão '
        'mecânica, um <strong>gateway concorrente em Go</strong> ingere tudo, e um '
        '<strong>motor em Python</strong> estima o desgaste de duas formas independentes para '
        'apontar quais pontos vão falhar primeiro. Este painel só lê o resultado já persistido '
        'no Supabase.</p>',
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
    fig2.update_yaxes(title_text="dano estimado")
    st.plotly_chart(_tema_grafico(fig2, 300), use_container_width=True, config={"displayModeBar": False})

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
