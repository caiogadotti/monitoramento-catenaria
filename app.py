"""Dashboard de monitoramento preditivo de catenária.

Lê direto do Supabase via REST com a chave anon (só select, RLS
garante isso, ver `src/persistencia/leitura.py`). Não fala com o
gateway nem com o motor de análise, só consome o que eles já
persistiram: é a ponta puramente de visualização do pipeline
`simulador -> gateway em Go -> motor de análise -> Supabase -> aqui`.
"""

from __future__ import annotations

import os

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from src.persistencia.leitura import buscar_alertas, buscar_leituras

st.set_page_config(
    page_title="Monitoramento Preditivo de Catenária",
    page_icon="⚡",
    layout="wide",
)

CORES_ESTADO = {"NORMAL": "#3fcf8e", "ATENCAO": "#f5b942", "CRITICO": "#ef4444"}


def _credenciais() -> tuple[str | None, str | None]:
    url = st.secrets.get("SUPABASE_URL", os.environ.get("SUPABASE_URL"))
    chave = st.secrets.get("SUPABASE_ANON_KEY", os.environ.get("SUPABASE_ANON_KEY"))
    return url, chave


@st.cache_data(ttl=10, show_spinner=False)
def _carregar_dados(url: str, chave: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    leituras = pd.DataFrame(buscar_leituras(url, chave, limite=2000))
    alertas = pd.DataFrame(buscar_alertas(url, chave, limite=200))

    if not leituras.empty:
        leituras["lido_em"] = pd.to_datetime(leituras["lido_em"])
        leituras = leituras.sort_values("lido_em")
    if not alertas.empty:
        alertas["disparado_em"] = pd.to_datetime(alertas["disparado_em"])
        alertas = alertas.sort_values("disparado_em", ascending=False)

    return leituras, alertas


def _ultimo_estado_por_sensor(leituras: pd.DataFrame) -> pd.DataFrame:
    return leituras.sort_values("lido_em").groupby("sensor_id").tail(1)


def main() -> None:
    st.title("⚡ Monitoramento Preditivo de Catenária")
    st.caption(
        "Rede de sensores simulada, ingerida por um gateway concorrente em Go, "
        "avaliada por dois estimadores de dano independentes em Python e "
        "persistida no Supabase. Ver o README do projeto pra arquitetura completa."
    )

    url, chave = _credenciais()
    if not url or not chave:
        st.error(
            "Faltam credenciais do Supabase. Preencha `SUPABASE_URL` e "
            "`SUPABASE_ANON_KEY` em `.streamlit/secrets.toml` (ver "
            "`.streamlit/secrets.toml.example`) ou nas variáveis de ambiente."
        )
        st.stop()

    try:
        leituras, alertas = _carregar_dados(url, chave)
    except Exception as erro:
        st.error(f"Falha ao consultar o Supabase: {erro}")
        st.stop()

    if leituras.empty:
        st.info(
            "Nenhuma leitura no banco ainda. Rode o pipeline com "
            "`--supabase`: `python scripts/motor_analise.py --arquivo leituras.ndjson --supabase`."
        )
        st.stop()

    ultimo = _ultimo_estado_por_sensor(leituras)

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Sensores monitorados", ultimo["sensor_id"].nunique())
    col2.metric("Em atenção", int((ultimo["estado"] == "ATENCAO").sum()))
    col3.metric("Em estado crítico", int((ultimo["estado"] == "CRITICO").sum()))
    col4.metric("Alertas registrados (histórico)", len(alertas))

    st.divider()

    col_esq, col_dir = st.columns([3, 2])

    with col_esq:
        st.subheader("Dano por posição na linha (km)")
        fig_mapa = px.scatter(
            ultimo,
            x="km",
            y="dano_ciclos",
            color="estado",
            color_discrete_map=CORES_ESTADO,
            hover_data=["sensor_id", "dano_espectral", "snr_db", "rul_segundos"],
            labels={"km": "Posição na linha (km)", "dano_ciclos": "Dano estimado (ciclos)"},
        )
        fig_mapa.update_traces(marker=dict(size=10, line=dict(width=1, color="#1a1a1a")))
        fig_mapa.update_layout(height=380, margin=dict(l=10, r=10, t=10, b=10))
        st.plotly_chart(fig_mapa, use_container_width=True)

    with col_dir:
        st.subheader("Sensores por estado")
        contagem = ultimo["estado"].value_counts().reindex(["NORMAL", "ATENCAO", "CRITICO"]).fillna(0)
        fig_pizza = go.Figure(
            data=[
                go.Pie(
                    labels=contagem.index,
                    values=contagem.values,
                    marker=dict(colors=[CORES_ESTADO[e] for e in contagem.index]),
                    hole=0.55,
                )
            ]
        )
        fig_pizza.update_layout(height=380, margin=dict(l=10, r=10, t=10, b=10), showlegend=True)
        st.plotly_chart(fig_pizza, use_container_width=True)

    st.divider()

    st.subheader("Sensores em risco (ordenados por dano)")
    risco = ultimo[ultimo["estado"] != "NORMAL"].sort_values("dano_ciclos", ascending=False)
    if risco.empty:
        st.success("Nenhum sensor em atenção ou crítico no momento.")
    else:
        risco_exibicao = risco[
            ["sensor_id", "km", "estado", "dano_ciclos", "dano_espectral", "snr_db", "rul_segundos", "ciclos_contados"]
        ].copy()
        risco_exibicao["rul_segundos"] = risco_exibicao["rul_segundos"].apply(
            lambda s: f"{s/3600:.1f}h" if pd.notna(s) else "n/d"
        )
        st.dataframe(
            risco_exibicao.rename(columns={
                "sensor_id": "Sensor", "km": "km", "estado": "Estado",
                "dano_ciclos": "Dano (ciclos)", "dano_espectral": "Dano (espectral)",
                "snr_db": "SNR (dB)", "rul_segundos": "RUL", "ciclos_contados": "Ciclos contados",
            }),
            use_container_width=True,
            hide_index=True,
        )

    st.divider()

    st.subheader("Histórico de um sensor")
    sensores = sorted(leituras["sensor_id"].unique())
    sensor_escolhido = st.selectbox("Sensor", sensores, index=0)
    historico = leituras[leituras["sensor_id"] == sensor_escolhido]

    fig_historico = go.Figure()
    fig_historico.add_trace(go.Scatter(
        x=historico["lido_em"], y=historico["dano_ciclos"],
        name="Dano por ciclos (Basquin/Miner)", mode="lines",
    ))
    fig_historico.add_trace(go.Scatter(
        x=historico["lido_em"], y=historico["dano_espectral"],
        name="Dano espectral (FFT)", mode="lines", line=dict(dash="dot"),
    ))
    fig_historico.update_layout(
        height=320, margin=dict(l=10, r=10, t=30, b=10),
        yaxis_title="Dano estimado", legend=dict(orientation="h", y=1.15),
    )
    st.plotly_chart(fig_historico, use_container_width=True)

    st.divider()

    st.subheader("Últimos alertas")
    if alertas.empty:
        st.info("Nenhum alerta registrado ainda.")
    else:
        st.dataframe(
            alertas[["disparado_em", "sensor_id", "km", "estado", "dano_ciclos", "dano_espectral"]].rename(
                columns={
                    "disparado_em": "Disparado em", "sensor_id": "Sensor", "km": "km",
                    "estado": "Estado", "dano_ciclos": "Dano (ciclos)", "dano_espectral": "Dano (espectral)",
                }
            ),
            use_container_width=True,
            hide_index=True,
        )

    st.caption("Atualiza sozinho a cada 10s (cache do Streamlit). Recarregue a página para forçar.")


if __name__ == "__main__":
    main()
