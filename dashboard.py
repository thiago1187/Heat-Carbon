# dashboard.py — Dashboard Heat Carbon (Streamlit)
# Projeto: Projetos 2 — Cesar School | Parceria Edenred / Taggy
#
# Visualiza o CO2e evitado pelo uso da tag de pedagio Taggy.
# IMPORTANTE: este arquivo NAO reimplementa a metodologia — ele importa e
# reaproveita as funcoes que ja existem em banco.py e metodologia.py.

import os
import sys
import json
import random
import unicodedata
from datetime import datetime, timedelta

import pandas as pd
import streamlit as st
import pydeck as pdk
import plotly.express as px

# Garante que os modulos do projeto sejam encontrados, igual ao cadastro.py
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

# --- Reuso do codigo ja existente no projeto ---------------------------------
from metodologia import (
    calcular_total,
    CONSUMO_EXTRA_POR_EVENTO,
    FATOR_EMISSAO_COMBUSTIVEL,
    ABSORCAO_ARVORE_KG_ANO,
)
from banco import (
    carregar_dados,
    inserir_perfil,
    inserir_registro,
    conectar,
)


# =============================================================================
# NORMALIZACAO DE NOMES DE BAIRRO
# Tira acento, espaco extra e caixa para cruzar o 'bairro' do banco com o
# 'EBAIRRNOMEOF' do geojson de forma robusta (ex.: "Várzea" == "varzea").
# =============================================================================
def norm_bairro(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    return s.lower().strip()


# =============================================================================
# CARBON MILES TAGGY — camada de incentivo do MVP
# Regra definida na pesquisa: 1 kg CO2e = 10 Carbon Points; 100 points = 1 mile.
# =============================================================================
CARBON_POINTS_POR_KG_CO2E = 10
CARBON_POINTS_POR_MILE = 100


# Estimativa de km por passagem de pedágio (média para rodovias de PE)
KM_MEDIO_POR_PASSAGEM = 30


def classificar_perfil_uso(passagens: int) -> str:
    if passagens <= 5:
        return "Casual"
    elif passagens <= 15:
        return "Frequente"
    return "Intensivo"


def calcular_carbon_points(co2e_kg):
    """Converte CO2e evitado em Carbon Points simulados."""
    return co2e_kg * CARBON_POINTS_POR_KG_CO2E


def calcular_carbon_miles(carbon_points):
    """Converte Carbon Points em Carbon Miles simuladas."""
    return carbon_points / CARBON_POINTS_POR_MILE


# =============================================================================
# GEOJSON DOS BAIRROS DE RECIFE (poligonos reais, chave EBAIRRNOMEOF)
# Fonte primaria do mapa coropletico. Cacheado por ser ~2 MB.
# =============================================================================
GEOJSON_PATH = os.path.join(BASE_DIR, "data", "bairros_recife.geojson")


@st.cache_data
def carregar_geojson():
    with open(GEOJSON_PATH, encoding="utf-8") as f:
        return json.load(f)


# =============================================================================
# COORDENADAS DOS BAIRROS DE RECIFE — FALLBACK
# Centroides aproximados (lat, lon). So usados se o mapa coropletico via
# geojson falhar; aqui viram pontos (ScatterplotLayer).
# =============================================================================
BAIRROS_COORD = {
    "Boa Viagem":      (-8.1196, -34.9059),
    "Pina":            (-8.0889, -34.8810),
    "Casa Forte":      (-8.0339, -34.9075),
    "Espinheiro":      (-8.0386, -34.8966),
    "Madalena":        (-8.0489, -34.9089),
    "Boa Vista":       (-8.0578, -34.8889),
    "Imbiribeira":     (-8.1011, -34.9183),
    "Várzea":          (-8.0489, -34.9628),
    "Torre":           (-8.0411, -34.9089),
    "Graças":          (-8.0436, -34.8975),
    "Afogados":        (-8.0744, -34.9089),
    "Santo Amaro":     (-8.0436, -34.8783),
    "Ilha do Retiro":  (-8.0625, -34.9039),
    "Derby":           (-8.0578, -34.8997),
    "Tamarineira":     (-8.0286, -34.9028),
    "Aflitos":         (-8.0356, -34.8978),
    "Cordeiro":        (-8.0419, -34.9286),
    "Bongi":           (-8.0700, -34.9300),
    "Recife":          (-8.0631, -34.8711),
    "Soledade":        (-8.0561, -34.8911),
    "Encruzilhada":    (-8.0314, -34.8917),
    "Caxangá":         (-8.0344, -34.9508),
}


# =============================================================================
# ACESSO AO BANCO (helpers locais — apenas leitura/limpeza, sem mexer no schema)
# =============================================================================
def contar_perfis() -> int:
    """Quantos perfis estao cadastrados na tabela perfil."""
    with conectar() as con:
        return con.execute("SELECT COUNT(*) FROM perfil").fetchone()[0]


def limpar_dados():
    """Apaga todos os registros e perfis (botao 'Limpar dados')."""
    with conectar() as con:
        con.execute("DELETE FROM registros")
        con.execute("DELETE FROM perfil")
        # zera o autoincremento, se a tabela de controle existir
        con.execute(
            "DELETE FROM sqlite_sequence WHERE name IN ('registros','perfil')"
        )


# =============================================================================
# GERADOR DE DADOS DE EXEMPLO
# Cria perfis ficticios e GRAVA usando inserir_perfil/inserir_registro reais —
# assim os numeros passam pela calcular_total de verdade e ficam coerentes com
# a metodologia (nao sao valores inventados na mao).
# =============================================================================
NOMES_FICTICIOS = [
    "Ana", "Bruno", "Carla", "Diego", "Elaine", "Felipe", "Gabriela", "Hugo",
    "Isabela", "João", "Karina", "Lucas", "Marina", "Nelson", "Olívia",
    "Paulo", "Quésia", "Rafael", "Sofia", "Tiago", "Úrsula", "Vitor",
    "Wesley", "Xênia", "Yuri", "Zélia",
]

# Pool de bairros do mock. Todos sao bairros reais de Recife, entao casam com
# o geojson e aparecem pintados no mapa. (O aviso de "bairro fora do mapa" do
# dashboard so dispara para nomes que nao existirem no geojson, ex.: typos.)
BAIRROS_MOCK = list(BAIRROS_COORD.keys()) + ["Curado", "Jordão", "Ibura"]


def gerar_dados_exemplo(qtd: int = 45):
    """Insere `qtd` registros ficticios variados no banco."""
    random.seed(42)  # reprodutivel: mesmo conjunto a cada clique
    tipos = list(CONSUMO_EXTRA_POR_EVENTO.keys())
    combustiveis = list(FATOR_EMISSAO_COMBUSTIVEL.keys())
    hoje = datetime.now()

    for i in range(qtd):
        nome = f"{random.choice(NOMES_FICTICIOS)} {random.randint(1, 99)}"
        bairro = random.choice(BAIRROS_MOCK)
        tipo_veiculo = random.choice(tipos)
        combustivel = random.choice(combustiveis)
        passagens = random.randint(1, 30)
        estacionamentos = random.randint(0, 25)
        # Distribui os registros nos últimos 90 dias para o gráfico temporal
        registrado_em = (hoje - timedelta(days=random.randint(0, 90))).strftime(
            "%Y-%m-%d %H:%M:%S"
        )

        # Calculo REAL pela metodologia do projeto
        resultado = calcular_total(
            passagens=passagens,
            usos_estacionamento=estacionamentos,
            tipo_veiculo=tipo_veiculo,
            combustivel=combustivel,
        )

        # Grava usando as funcoes existentes do banco
        pid = inserir_perfil(nome, bairro, tipo_veiculo, combustivel)
        inserir_registro(
            perfil_id=pid,
            passagens=passagens,
            estacionamentos=estacionamentos,
            co2e_pedagio_kg=resultado["co2e_pedagio_kg"],
            co2e_estac_kg=resultado["co2e_estacionamento_kg"],
            co2e_total_kg=resultado["co2e_total_kg"],
            registrado_em=registrado_em,
        )


def cadastrar_uso_taggy(
    nome: str,
    bairro: str,
    tipo_veiculo: str,
    combustivel: str,
    passagens: int,
    estacionamentos: int,
) -> dict:
    """Calcula CO2e e salva um registro vindo do formulario Streamlit."""
    resultado = calcular_total(
        passagens=passagens,
        usos_estacionamento=estacionamentos,
        tipo_veiculo=tipo_veiculo,
        combustivel=combustivel,
    )

    pid = inserir_perfil(nome, bairro, tipo_veiculo, combustivel)
    inserir_registro(
        perfil_id=pid,
        passagens=passagens,
        estacionamentos=estacionamentos,
        co2e_pedagio_kg=resultado["co2e_pedagio_kg"],
        co2e_estac_kg=resultado["co2e_estacionamento_kg"],
        co2e_total_kg=resultado["co2e_total_kg"],
    )
    return resultado


# =============================================================================
# CONFIGURACAO DA PAGINA
# =============================================================================
st.set_page_config(
    page_title="Heat Carbon — Dashboard Taggy",
    page_icon="🌿",
    layout="wide",
)


def enriquecer_carbon_miles(dados: pd.DataFrame) -> pd.DataFrame:
    """Adiciona Carbon Points e Carbon Miles ao dataframe carregado do banco."""
    if dados.empty:
        return dados
    dados = dados.copy()
    dados["registrado_em"] = pd.to_datetime(dados["registrado_em"])
    dados["carbon_points"] = calcular_carbon_points(dados["co2e_total_kg"])
    dados["carbon_miles"] = calcular_carbon_miles(dados["carbon_points"])
    return dados


def aplicar_filtros(
    dados: pd.DataFrame,
    bairros: list[str],
    tipos_veiculo: list[str],
    combustiveis: list[str],
    intervalo_datas,
) -> pd.DataFrame:
    """Filtra os registros para exploração do dashboard sem alterar o banco."""
    filtrado = dados.copy()

    if bairros:
        filtrado = filtrado[filtrado["bairro"].isin(bairros)]
    if tipos_veiculo:
        filtrado = filtrado[filtrado["tipo_veiculo"].isin(tipos_veiculo)]
    if combustiveis:
        filtrado = filtrado[filtrado["combustivel"].isin(combustiveis)]
    if isinstance(intervalo_datas, (list, tuple)) and len(intervalo_datas) == 2:
        data_inicio, data_fim = intervalo_datas
        datas = filtrado["registrado_em"].dt.date
        filtrado = filtrado[(datas >= data_inicio) & (datas <= data_fim)]

    return filtrado


def montar_ranking_usuarios(dados: pd.DataFrame) -> pd.DataFrame:
    ranking = (
        dados.groupby("nome")
        .agg(
            registros=("co2e_total_kg", "count"),
            co2e_total_kg=("co2e_total_kg", "sum"),
            carbon_points=("carbon_points", "sum"),
            carbon_miles=("carbon_miles", "sum"),
        )
        .reset_index()
        .sort_values("carbon_points", ascending=False)
    )
    ranking["co2e_total_kg"] = ranking["co2e_total_kg"].round(2)
    ranking["carbon_points"] = ranking["carbon_points"].round(0)
    ranking["carbon_miles"] = ranking["carbon_miles"].round(2)
    return ranking


def montar_historico_carbon(dados: pd.DataFrame) -> pd.DataFrame:
    historico = dados[
        [
            "nome",
            "bairro",
            "tipo_veiculo",
            "combustivel",
            "passagens",
            "estacionamentos",
            "co2e_total_kg",
            "carbon_points",
            "carbon_miles",
            "registrado_em",
        ]
    ].sort_values("registrado_em", ascending=False)
    historico["co2e_total_kg"] = historico["co2e_total_kg"].round(2)
    historico["carbon_points"] = historico["carbon_points"].round(0)
    historico["carbon_miles"] = historico["carbon_miles"].round(2)
    return historico


def montar_recompensas(total_carbon_points: float) -> pd.DataFrame:
    recompensas = pd.DataFrame(
        [
            {"carbon_points": 500, "beneficio": "Selo Motorista Verde"},
            {"carbon_points": 1000, "beneficio": "Certificado digital ESG"},
            {"carbon_points": 2500, "beneficio": "Voucher simbólico"},
            {"carbon_points": 5000, "beneficio": "Conversão simulada em milhas"},
            {"carbon_points": 10000, "beneficio": "Destaque no ranking sustentável"},
        ]
    )
    recompensas["status"] = recompensas["carbon_points"].map(
        lambda pontos: "Liberado" if total_carbon_points >= pontos else "A desbloquear"
    )
    return recompensas


def montar_resumo_bairro(dados: pd.DataFrame) -> pd.DataFrame:
    resumo = (
        dados.groupby("bairro")
        .agg(
            registros=("co2e_total_kg", "count"),
            passagens=("passagens", "sum"),
            estacionamentos=("estacionamentos", "sum"),
            co2e_total_kg=("co2e_total_kg", "sum"),
            carbon_points=("carbon_points", "sum"),
            carbon_miles=("carbon_miles", "sum"),
        )
        .reset_index()
        .sort_values("co2e_total_kg", ascending=False)
    )
    resumo["co2e_total_kg"] = resumo["co2e_total_kg"].round(2)
    resumo["carbon_points"] = resumo["carbon_points"].round(0)
    resumo["carbon_miles"] = resumo["carbon_miles"].round(2)
    return resumo


def render_analise_avancada(dados: pd.DataFrame):
    st.subheader("Análise avançada")

    dados_ext = dados.copy()
    dados_ext["km_estimado"] = dados_ext["passagens"] * KM_MEDIO_POR_PASSAGEM
    dados_ext["perfil_uso"] = dados_ext["passagens"].apply(classificar_perfil_uso)

    (
        aba_dispersao,
        aba_temporal,
        aba_dist,
        aba_ranking,
        aba_comparacao,
    ) = st.tabs(
        [
            "Dispersão",
            "Evolução temporal",
            "Distribuição",
            "Ranking ambiental",
            "Com vs Sem Taggy",
        ]
    )

    # ── 1 & 2 · Dispersão ─────────────────────────────────────────────────────
    with aba_dispersao:
        st.markdown("##### Frequência de uso vs CO₂ evitado")
        st.caption("Mostra se quem usa mais a tag gera mais impacto positivo.")
        fig_scatter1 = px.scatter(
            dados_ext,
            x="passagens",
            y="co2e_total_kg",
            color="tipo_veiculo",
            size="co2e_total_kg",
            hover_data=["nome", "bairro", "combustivel"],
            labels={
                "passagens": "Passagens de pedágio",
                "co2e_total_kg": "CO₂e evitado (kg)",
                "tipo_veiculo": "Tipo de veículo",
            },
            title="Quem usa mais a Taggy evita mais CO₂?",
        )
        st.plotly_chart(fig_scatter1, use_container_width=True)

        st.markdown("##### Distância estimada vs CO₂ evitado")
        st.caption(
            f"Distância estimada: {KM_MEDIO_POR_PASSAGEM} km médios por passagem "
            "(média rodovias PE). Cada combustível forma um cluster próprio."
        )
        fig_scatter2 = px.scatter(
            dados_ext,
            x="km_estimado",
            y="co2e_total_kg",
            color="combustivel",
            symbol="tipo_veiculo",
            hover_data=["nome", "passagens"],
            labels={
                "km_estimado": "Distância estimada (km)",
                "co2e_total_kg": "CO₂e evitado (kg)",
                "combustivel": "Combustível",
                "tipo_veiculo": "Veículo",
            },
            title="Distância percorrida vs emissão evitada por combustível",
        )
        st.plotly_chart(fig_scatter2, use_container_width=True)

    # ── 3 · Evolução temporal ─────────────────────────────────────────────────
    with aba_temporal:
        st.markdown("##### CO₂ evitado ao longo do tempo")
        granularidade = st.radio(
            "Granularidade", ["Semanal", "Mensal"], horizontal=True, key="gran_temporal"
        )
        freq = "W" if granularidade == "Semanal" else "ME"
        dados_tempo = dados_ext.copy()
        dados_tempo["periodo"] = (
            dados_tempo["registrado_em"].dt.to_period(freq).dt.start_time
        )
        co2_periodo = (
            dados_tempo.groupby("periodo")["co2e_total_kg"].sum().reset_index()
        )
        co2_periodo.columns = ["periodo", "co2e_total_kg"]
        co2_periodo["co2e_acumulado"] = co2_periodo["co2e_total_kg"].cumsum()

        if len(co2_periodo) <= 1:
            st.info(
                "Todos os registros têm a mesma data — clique em 'Limpar dados' "
                "e depois 'Gerar dados de exemplo' para distribuir no tempo."
            )
        else:
            col_area1, col_area2 = st.columns(2)
            with col_area1:
                fig_area = px.area(
                    co2_periodo,
                    x="periodo",
                    y="co2e_total_kg",
                    labels={
                        "periodo": "Período",
                        "co2e_total_kg": "CO₂e evitado (kg)",
                    },
                    title=f"CO₂e evitado por {granularidade.lower()[:-2]}",
                    color_discrete_sequence=["#19d3f3"],
                )
                st.plotly_chart(fig_area, use_container_width=True)
            with col_area2:
                fig_acum = px.area(
                    co2_periodo,
                    x="periodo",
                    y="co2e_acumulado",
                    labels={
                        "periodo": "Período",
                        "co2e_acumulado": "CO₂e acumulado (kg)",
                    },
                    title="CO₂e acumulado",
                    color_discrete_sequence=["#00cc96"],
                )
                st.plotly_chart(fig_acum, use_container_width=True)

    # ── 4 · Violino ───────────────────────────────────────────────────────────
    with aba_dist:
        st.markdown("##### Distribuição de CO₂ evitado por perfil de uso")
        st.caption("Casual: ≤ 5 passagens · Frequente: 6–15 · Intensivo: > 15")
        fig_violin = px.violin(
            dados_ext,
            x="perfil_uso",
            y="co2e_total_kg",
            color="perfil_uso",
            box=True,
            points="all",
            hover_data=["nome", "tipo_veiculo"],
            labels={
                "perfil_uso": "Perfil de uso",
                "co2e_total_kg": "CO₂e evitado (kg)",
            },
            title="Variação de impacto ambiental por perfil",
            category_orders={"perfil_uso": ["Casual", "Frequente", "Intensivo"]},
        )
        st.plotly_chart(fig_violin, use_container_width=True)

    # ── 5 · Ranking ambiental ─────────────────────────────────────────────────
    with aba_ranking:
        st.markdown("##### Ranking ambiental com níveis ESG")

        def tier_badge(points: float) -> str:
            if points >= 10000:
                return "Platina"
            elif points >= 5000:
                return "Ouro"
            elif points >= 2500:
                return "Prata"
            elif points >= 500:
                return "Bronze"
            return "Iniciante"

        ranking_env = montar_ranking_usuarios(dados_ext)
        ranking_env["nivel"] = ranking_env["carbon_points"].map(tier_badge)
        ranking_env.insert(0, "pos", range(1, len(ranking_env) + 1))
        ranking_env = ranking_env[
            ["pos", "nome", "nivel", "co2e_total_kg", "carbon_points", "carbon_miles", "registros"]
        ]
        ranking_env.columns = [
            "#", "Usuário", "Nível", "CO₂e (kg)", "Carbon Points", "Carbon Miles", "Registros"
        ]

        st.dataframe(ranking_env, width="stretch", hide_index=True)

        _rank_src = montar_ranking_usuarios(dados_ext).head(15)
        _rank_src["nivel"] = _rank_src["carbon_points"].map(tier_badge)
        fig_rank_env = px.bar(
            _rank_src,
            x="co2e_total_kg",
            y="nome",
            orientation="h",
            color="nivel",
            labels={
                "nome": "Usuário",
                "co2e_total_kg": "CO₂e evitado (kg)",
                "nivel": "Nível",
            },
            title="Top 15 — Ranking Ambiental",
            color_discrete_map={
                "Platina": "#e5e4e2",
                "Ouro": "#ffd700",
                "Prata": "#c0c0c0",
                "Bronze": "#cd7f32",
                "Iniciante": "#90ee90",
            },
            category_orders={
                "nivel": ["Platina", "Ouro", "Prata", "Bronze", "Iniciante"]
            },
        )
        fig_rank_env.update_layout(yaxis={"categoryorder": "total ascending"})
        st.plotly_chart(fig_rank_env, use_container_width=True)

    # ── 6 · Comparação com vs sem Taggy ───────────────────────────────────────
    with aba_comparacao:
        st.markdown("##### Com Taggy vs Sem Taggy")
        st.caption(
            "Sem Taggy, cada passagem exige desaceleração → marcha lenta → aceleração, "
            "gerando combustível extra queimado. Com a tag, esse ciclo não acontece."
        )

        total_pedagio = dados_ext["co2e_pedagio_kg"].sum()
        total_estac = dados_ext["co2e_estac_kg"].sum()
        total_evitado = total_pedagio + total_estac

        m1, m2, m3 = st.columns(3)
        m1.metric("CO₂e total evitado", f"{total_evitado:,.2f} kg")
        m2.metric("Evitado em pedágios", f"{total_pedagio:,.2f} kg")
        m3.metric("Evitado em estacionamentos", f"{total_estac:,.2f} kg")

        comp_df = pd.DataFrame(
            [
                {"cenário": "Com Taggy", "origem": "Pedágio", "co2e_kg": 0.0},
                {"cenário": "Com Taggy", "origem": "Estacionamento", "co2e_kg": 0.0},
                {
                    "cenário": "Sem Taggy",
                    "origem": "Pedágio",
                    "co2e_kg": round(total_pedagio, 2),
                },
                {
                    "cenário": "Sem Taggy",
                    "origem": "Estacionamento",
                    "co2e_kg": round(total_estac, 2),
                },
            ]
        )
        fig_comp = px.bar(
            comp_df,
            x="cenário",
            y="co2e_kg",
            color="origem",
            barmode="stack",
            text_auto=".2f",
            labels={"cenário": "Cenário", "co2e_kg": "CO₂e (kg)", "origem": "Fonte"},
            title=f"{total_evitado:,.1f} kg CO₂e evitado graças à Taggy",
            color_discrete_map={"Pedágio": "#ef553b", "Estacionamento": "#636efa"},
        )
        st.plotly_chart(fig_comp, use_container_width=True)

        st.markdown("##### Detalhe por usuário (top 15)")
        user_comp = (
            dados_ext.groupby("nome")
            .agg(
                co2e_pedagio_kg=("co2e_pedagio_kg", "sum"),
                co2e_estac_kg=("co2e_estac_kg", "sum"),
            )
            .reset_index()
            .assign(co2e_total=lambda d: d["co2e_pedagio_kg"] + d["co2e_estac_kg"])
            .sort_values("co2e_total", ascending=False)
            .head(15)
        )
        fig_user_comp = px.bar(
            user_comp,
            x="nome",
            y=["co2e_pedagio_kg", "co2e_estac_kg"],
            barmode="stack",
            labels={
                "nome": "Usuário",
                "value": "CO₂e evitado (kg)",
                "variable": "Origem",
            },
            title="Top 15 usuários — pedágio vs estacionamento",
            color_discrete_map={
                "co2e_pedagio_kg": "#ef553b",
                "co2e_estac_kg": "#636efa",
            },
        )
        fig_user_comp.for_each_trace(
            lambda t: t.update(
                name="Pedágio" if t.name == "co2e_pedagio_kg" else "Estacionamento"
            )
        )
        st.plotly_chart(fig_user_comp, use_container_width=True)


def render_kpis(dados: pd.DataFrame):
    total_co2 = dados["co2e_total_kg"].sum()
    total_carbon_points = dados["carbon_points"].sum()
    total_carbon_miles = dados["carbon_miles"].sum()
    arvores = total_co2 / ABSORCAO_ARVORE_KG_ANO
    total_passagens = int(dados["passagens"].sum())
    qtd_perfis = dados["nome"].nunique()

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("CO₂e evitado", f"{total_co2:,.1f} kg")
    c2.metric("Carbon Points", f"{total_carbon_points:,.0f}")
    c3.metric("Carbon Miles", f"{total_carbon_miles:,.2f}")
    c4.metric("Equivale a", f"{arvores:,.1f} árvores/ano")
    c5.metric("Perfis", f"{qtd_perfis}")
    c6.metric("Passagens", f"{total_passagens}")


def render_formulario_cadastro():
    st.subheader("Cadastrar uso da Taggy")
    st.caption("Os dados entram direto no SQLite local e atualizam o dashboard.")

    with st.form("form_cadastro_uso", clear_on_submit=True):
        col_a, col_b = st.columns(2)
        with col_a:
            nome_form = st.text_input("Nome", placeholder="Ex.: Marina")
            bairro_form = st.text_input("Bairro em Recife", placeholder="Ex.: Boa Viagem")
            tipo_veiculo_form = st.selectbox(
                "Tipo de veículo",
                list(CONSUMO_EXTRA_POR_EVENTO.keys()),
                key="cadastro_tipo_veiculo",
            )
        with col_b:
            combustivel_form = st.selectbox(
                "Combustível",
                list(FATOR_EMISSAO_COMBUSTIVEL.keys()),
                key="cadastro_combustivel",
            )
            passagens_form = st.number_input(
                "Passagens de pedágio", min_value=0, value=1, step=1
            )
            estacionamentos_form = st.number_input(
                "Usos em estacionamento", min_value=0, value=0, step=1
            )

        salvar_form = st.form_submit_button("Salvar registro", width="stretch")

    if salvar_form:
        nome = nome_form.strip() or "Anônimo"
        bairro = bairro_form.strip()
        passagens = int(passagens_form)
        estacionamentos = int(estacionamentos_form)

        if not bairro:
            st.error("Informe o bairro para salvar o registro.")
        elif passagens == 0 and estacionamentos == 0:
            st.error("Informe pelo menos uma passagem ou uso em estacionamento.")
        else:
            resultado = cadastrar_uso_taggy(
                nome=nome,
                bairro=bairro,
                tipo_veiculo=tipo_veiculo_form,
                combustivel=combustivel_form,
                passagens=passagens,
                estacionamentos=estacionamentos,
            )
            st.session_state.dados_limpos = False
            st.session_state.feedback_cadastro = (
                "Registro salvo: "
                f"{resultado['co2e_total_kg']} kg CO₂e evitado, "
                f"{calcular_carbon_points(resultado['co2e_total_kg']):,.0f} "
                "Carbon Points."
            )
            st.rerun()


def render_calculadora():
    st.subheader("Calculadora rápida")
    st.caption("Simula o impacto antes de salvar um registro.")

    col_in, col_out = st.columns([1, 1])
    with col_in:
        veiculo_calc = st.selectbox(
            "Tipo de veículo",
            list(CONSUMO_EXTRA_POR_EVENTO.keys()),
            key="calc_tipo_veiculo",
        )
        combustivel_calc = st.selectbox(
            "Combustível",
            list(FATOR_EMISSAO_COMBUSTIVEL.keys()),
            key="calc_combustivel",
        )
        passagens_calc = st.number_input(
            "Passagens de pedágio com Taggy", min_value=0, value=20, step=1
        )
        estac_calc = st.number_input(
            "Usos de estacionamento com Taggy", min_value=0, value=8, step=1
        )

    resultado_calc = calcular_total(
        passagens=int(passagens_calc),
        usos_estacionamento=int(estac_calc),
        tipo_veiculo=veiculo_calc,
        combustivel=combustivel_calc,
    )
    points_calc = calcular_carbon_points(resultado_calc["co2e_total_kg"])
    miles_calc = calcular_carbon_miles(points_calc)

    with col_out:
        st.metric("CO₂e total evitado", f"{resultado_calc['co2e_total_kg']} kg")
        st.write(f"- Pedágios: **{resultado_calc['co2e_pedagio_kg']} kg**")
        st.write(f"- Estacionamentos: **{resultado_calc['co2e_estacionamento_kg']} kg**")
        st.write(f"- Equivale a **{resultado_calc['equivalente_arvores']} árvore(s)/ano**")
        st.write(f"- Gera **{points_calc:,.0f} Carbon Points**")
        st.write(f"- Converte em **{miles_calc:,.2f} Carbon Miles simuladas**")


def render_cadastro(dados: pd.DataFrame):
    if "feedback_cadastro" in st.session_state:
        st.success(st.session_state.pop("feedback_cadastro"))

    render_formulario_cadastro()
    st.divider()
    render_calculadora()

    if not dados.empty:
        st.divider()
        st.subheader("Últimos registros")
        st.dataframe(montar_historico_carbon(dados).head(8), width="stretch", hide_index=True)


def render_carteira(dados: pd.DataFrame):
    st.subheader("Carteira Carbon Miles")
    st.caption(
        "Conversão simulada para o MVP: "
        f"1 kg de CO₂e = {CARBON_POINTS_POR_KG_CO2E} Carbon Points · "
        f"{CARBON_POINTS_POR_MILE} Carbon Points = 1 Carbon Mile."
    )

    total_carbon_points = dados["carbon_points"].sum()
    total_carbon_miles = dados["carbon_miles"].sum()
    ranking_usuarios = montar_ranking_usuarios(dados)
    historico_carbon = montar_historico_carbon(dados)
    recompensas = montar_recompensas(total_carbon_points)

    aba_saldo, aba_recompensas, aba_historico, aba_ranking = st.tabs(
        ["Saldo", "Recompensas", "Histórico", "Ranking"]
    )

    with aba_saldo:
        s1, s2, s3 = st.columns(3)
        s1.metric("Saldo Carbon Points", f"{total_carbon_points:,.0f}")
        s2.metric("Carbon Miles simuladas", f"{total_carbon_miles:,.2f}")
        s3.metric("Usuários no ranking", f"{len(ranking_usuarios)}")

    with aba_recompensas:
        st.dataframe(recompensas, width="stretch", hide_index=True)

    with aba_historico:
        st.dataframe(historico_carbon, width="stretch", hide_index=True)

    with aba_ranking:
        st.dataframe(ranking_usuarios, width="stretch", hide_index=True)
        fig_ranking = px.bar(
            ranking_usuarios.head(15),
            x="carbon_points",
            y="nome",
            orientation="h",
            color="carbon_points",
            color_continuous_scale="Greens",
            labels={
                "nome": "Usuário",
                "carbon_points": "Carbon Points",
            },
            title="Ranking por Carbon Points",
        )
        fig_ranking.update_layout(yaxis={"categoryorder": "total ascending"})
        st.plotly_chart(fig_ranking, use_container_width=True)


def render_graficos(dados: pd.DataFrame):
    st.subheader("Gráficos e mapa")

    por_bairro = (
        dados.groupby("bairro")["co2e_total_kg"].sum().reset_index()
        .sort_values("co2e_total_kg", ascending=False)
    )
    co2_por_norm = (
        dados.assign(_chave=dados["bairro"].map(norm_bairro))
        .groupby("_chave")["co2e_total_kg"].sum()
        .to_dict()
    )

    col_mapa, col_rank = st.columns([1.4, 1])
    with col_mapa:
        try:
            geo = carregar_geojson()
            max_co2 = max(co2_por_norm.values()) if co2_por_norm else 0.0

            feats = []
            nomes_geo = set()
            for f in geo["features"]:
                nome_of = f["properties"].get("EBAIRRNOMEOF", "")
                chave = norm_bairro(nome_of)
                nomes_geo.add(chave)
                co2 = co2_por_norm.get(chave, 0.0)
                t = (co2 / max_co2) if max_co2 else 0.0

                if co2 > 0:
                    cor = [
                        int(255 + (0 - 255) * t),
                        int(255 + (104 - 255) * t),
                        int(204 + (55 - 204) * t),
                        190,
                    ]
                else:
                    cor = [235, 235, 235, 60]

                feats.append({
                    "type": "Feature",
                    "geometry": f["geometry"],
                    "bairro": nome_of,
                    "co2e": round(co2, 2),
                    "properties": {"fill_color": cor},
                })

            camada = pdk.Layer(
                "GeoJsonLayer",
                data={"type": "FeatureCollection", "features": feats},
                get_fill_color="properties.fill_color",
                get_line_color=[120, 120, 120],
                line_width_min_pixels=0.5,
                stroked=True,
                filled=True,
                pickable=True,
            )
            st.pydeck_chart(
                pdk.Deck(
                    layers=[camada],
                    initial_view_state=pdk.ViewState(
                        latitude=-8.05, longitude=-34.92, zoom=11.0
                    ),
                    map_style="light",
                    tooltip={"text": "{bairro}\nCO₂e evitado: {co2e} kg"},
                )
            )
            st.caption("Tom mais escuro = mais CO₂e evitado. Cinza = sem registros.")

            sem_match = sorted(
                {b for b in dados["bairro"].unique() if norm_bairro(b) not in nomes_geo}
            )
            if sem_match:
                st.warning(
                    "Bairros sem polígono no mapa: " + ", ".join(sem_match)
                )

        except Exception as e:
            st.warning(f"Mapa coroplético indisponível; usando pontos aproximados ({e}).")
            pts = por_bairro.copy()
            pts["lat"] = pts["bairro"].map(lambda b: BAIRROS_COORD.get(b, (None, None))[0])
            pts["lon"] = pts["bairro"].map(lambda b: BAIRROS_COORD.get(b, (None, None))[1])
            pts = pts.dropna(subset=["lat", "lon"])
            if pts.empty:
                st.info("Sem bairros com coordenada conhecida para o mapa de pontos.")
            else:
                mx = pts["co2e_total_kg"].max()
                pts["raio"] = 250 + (pts["co2e_total_kg"] / mx) * 1600
                scatter = pdk.Layer(
                    "ScatterplotLayer",
                    data=pts,
                    get_position="[lon, lat]",
                    get_radius="raio",
                    get_fill_color="[200, 30, 0, 140]",
                    pickable=True,
                )
                st.pydeck_chart(
                    pdk.Deck(
                        layers=[scatter],
                        initial_view_state=pdk.ViewState(
                            latitude=-8.05, longitude=-34.90, zoom=11.2
                        ),
                        map_style="light",
                        tooltip={"text": "{bairro}\nCO₂e: {co2e_total_kg} kg"},
                    )
                )

    with col_rank:
        st.caption("Ranking de bairros por CO₂e evitado (kg)")
        fig_bairros = px.bar(
            por_bairro.head(15),
            x="co2e_total_kg",
            y="bairro",
            orientation="h",
            color="co2e_total_kg",
            color_continuous_scale="Greens",
            labels={
                "bairro": "Bairro",
                "co2e_total_kg": "CO₂e evitado (kg)",
            },
        )
        fig_bairros.update_layout(yaxis={"categoryorder": "total ascending"})
        st.plotly_chart(fig_bairros, use_container_width=True)

    st.divider()
    g1, g2, g3 = st.columns(3)
    with g1:
        st.caption("Por tipo de veículo")
        por_veiculo = (
            dados.groupby("tipo_veiculo")["co2e_total_kg"]
            .sum()
            .reset_index()
            .sort_values("co2e_total_kg", ascending=False)
        )
        fig_veiculo = px.bar(
            por_veiculo,
            x="tipo_veiculo",
            y="co2e_total_kg",
            color="tipo_veiculo",
            labels={
                "tipo_veiculo": "Tipo de veículo",
                "co2e_total_kg": "CO₂e evitado (kg)",
            },
        )
        fig_veiculo.update_layout(showlegend=False)
        st.plotly_chart(fig_veiculo, use_container_width=True)
    with g2:
        st.caption("Por combustível")
        por_combustivel = (
            dados.groupby("combustivel")["co2e_total_kg"]
            .sum()
            .reset_index()
            .sort_values("co2e_total_kg", ascending=False)
        )
        fig_combustivel = px.bar(
            por_combustivel,
            x="combustivel",
            y="co2e_total_kg",
            color="combustivel",
            labels={
                "combustivel": "Combustível",
                "co2e_total_kg": "CO₂e evitado (kg)",
            },
        )
        fig_combustivel.update_layout(showlegend=False)
        st.plotly_chart(fig_combustivel, use_container_width=True)
    with g3:
        st.caption("Pedágio vs. Estacionamento")
        comparacao = pd.DataFrame(
            [
                {"origem": "pedágio", "co2e_kg": dados["co2e_pedagio_kg"].sum()},
                {
                    "origem": "estacionamento",
                    "co2e_kg": dados["co2e_estac_kg"].sum(),
                },
            ]
        )
        fig_comparacao = px.pie(
            comparacao,
            names="origem",
            values="co2e_kg",
            hole=0.45,
            labels={"origem": "Origem", "co2e_kg": "CO₂e evitado (kg)"},
        )
        st.plotly_chart(fig_comparacao, use_container_width=True)


def render_relatorios(dados: pd.DataFrame):
    st.subheader("Relatórios")
    st.caption("Exporta dados completos e consolidados para auditoria ESG.")

    resumo_bairro = montar_resumo_bairro(dados)
    col_r1, col_r2 = st.columns(2)
    with col_r1:
        st.download_button(
            "Baixar relatório completo (CSV)",
            data=dados.to_csv(index=False).encode("utf-8-sig"),
            file_name="heatcarbon_registros.csv",
            mime="text/csv",
            width="stretch",
        )
    with col_r2:
        st.download_button(
            "Baixar consolidado por bairro (CSV)",
            data=resumo_bairro.to_csv(index=False).encode("utf-8-sig"),
            file_name="heatcarbon_por_bairro.csv",
            mime="text/csv",
            width="stretch",
        )

    st.subheader("Consolidado por bairro")
    st.dataframe(resumo_bairro, width="stretch", hide_index=True)

    with st.expander("Ver dados brutos"):
        st.dataframe(dados, width="stretch", hide_index=True)


# Estado de sessao: controla se o usuario esvaziou o banco de proposito
if "dados_limpos" not in st.session_state:
    st.session_state.dados_limpos = False


with st.sidebar:
    st.header("Heat Carbon")
    pagina = st.radio(
        "Menu",
        ["Menu / Cadastro", "Carteira / Marketplace", "Gráficos", "Análise Avançada", "Relatórios"],
    )

    st.divider()
    st.caption("Banco local: data/taggy.db")

    if st.button("Gerar dados de exemplo", width="stretch"):
        gerar_dados_exemplo()
        st.session_state.dados_limpos = False
        st.rerun()

    if st.button("Limpar dados", width="stretch"):
        limpar_dados()
        st.session_state.dados_limpos = True
        st.rerun()


# Regra "nunca abrir numa tela vazia": se o banco esta vazio E o usuario nao
# pediu para limpar, semeia dados de exemplo automaticamente na 1a abertura.
if contar_perfis() == 0 and not st.session_state.dados_limpos:
    gerar_dados_exemplo()


df = enriquecer_carbon_miles(carregar_dados())


if not df.empty:
    with st.sidebar:
        st.divider()
        st.subheader("Filtros")
        bairros_filtro = st.multiselect(
            "Bairro",
            sorted(df["bairro"].dropna().unique()),
            placeholder="Todos os bairros",
        )
        veiculos_filtro = st.multiselect(
            "Tipo de veículo",
            sorted(df["tipo_veiculo"].dropna().unique()),
            placeholder="Todos os veículos",
        )
        combustiveis_filtro = st.multiselect(
            "Combustível",
            sorted(df["combustivel"].dropna().unique()),
            placeholder="Todos os combustíveis",
        )

        data_min = df["registrado_em"].dt.date.min()
        data_max = df["registrado_em"].dt.date.max()
        intervalo_datas = st.date_input(
            "Período",
            value=(data_min, data_max),
            min_value=data_min,
            max_value=data_max,
        )

    df_filtrado = aplicar_filtros(
        dados=df,
        bairros=bairros_filtro,
        tipos_veiculo=veiculos_filtro,
        combustiveis=combustiveis_filtro,
        intervalo_datas=intervalo_datas,
    )
else:
    df_filtrado = df


st.title("Heat Carbon — CO₂e evitado com a Taggy")
st.caption(
    "Projetos 2 — Cesar School · Parceria Edenred/Taggy · "
    "emissões evitadas, Carbon Miles e relatórios ESG."
)

if not df_filtrado.empty:
    render_kpis(df_filtrado)
    st.divider()
elif not df.empty:
    st.warning("Nenhum registro encontrado para os filtros selecionados.")

if pagina == "Menu / Cadastro":
    render_cadastro(df_filtrado if not df_filtrado.empty else df)
elif df.empty:
    st.info("Nenhum dado no banco. Cadastre um uso ou gere dados de exemplo.")
elif df_filtrado.empty:
    st.info("Ajuste os filtros na barra lateral para visualizar dados.")
else:
    if pagina == "Carteira / Marketplace":
        render_carteira(df_filtrado)
    elif pagina == "Gráficos":
        render_graficos(df_filtrado)
    elif pagina == "Análise Avançada":
        render_analise_avancada(df_filtrado)
    elif pagina == "Relatórios":
        render_relatorios(df_filtrado)
