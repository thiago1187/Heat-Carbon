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

import pandas as pd
import streamlit as st
import pydeck as pdk

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

    for i in range(qtd):
        nome = f"{random.choice(NOMES_FICTICIOS)} {random.randint(1, 99)}"
        bairro = random.choice(BAIRROS_MOCK)
        tipo_veiculo = random.choice(tipos)
        combustivel = random.choice(combustiveis)
        passagens = random.randint(1, 30)
        estacionamentos = random.randint(0, 25)

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
        )


# =============================================================================
# CONFIGURACAO DA PAGINA
# =============================================================================
st.set_page_config(
    page_title="Heat Carbon — Dashboard Taggy",
    page_icon="🌿",
    layout="wide",
)


# =============================================================================
# SIDEBAR — controles de dados
# =============================================================================
with st.sidebar:
    st.header("⚙️ Dados")
    st.caption("Banco local: data/taggy.db")

    if st.button("🌱 Gerar dados de exemplo", use_container_width=True):
        gerar_dados_exemplo()
        st.session_state.dados_limpos = False
        st.success("Dados de exemplo gerados!")
        st.rerun()

    if st.button("🗑️ Limpar dados", use_container_width=True):
        limpar_dados()
        st.session_state.dados_limpos = True  # impede o auto-preenchimento
        st.warning("Banco esvaziado.")
        st.rerun()


# Estado de sessao: controla se o usuario esvaziou o banco de proposito
if "dados_limpos" not in st.session_state:
    st.session_state.dados_limpos = False

# Regra "nunca abrir numa tela vazia": se o banco esta vazio E o usuario nao
# pediu para limpar, semeia dados de exemplo automaticamente na 1a abertura.
if contar_perfis() == 0 and not st.session_state.dados_limpos:
    gerar_dados_exemplo()

# Carrega os dados (funcao do projeto)
df = carregar_dados()


# =============================================================================
# CABECALHO
# =============================================================================
st.title("🌿 Heat Carbon — CO₂e evitado com a Taggy")
st.caption(
    "Projetos 2 — Cesar School · Parceria Edenred/Taggy · "
    "Emissões evitadas pelo uso da tag de pedágio em Recife"
)

# Se o banco esta vazio (usuario limpou), mostra orientacao e para por aqui.
if df.empty:
    st.info(
        "Nenhum dado no banco. Use **🌱 Gerar dados de exemplo** na barra "
        "lateral, ou cadastre usuários com `python cadastro.py`."
    )
    st.stop()


# =============================================================================
# 1) KPIs NO TOPO
# =============================================================================
total_co2 = df["co2e_total_kg"].sum()
arvores = total_co2 / ABSORCAO_ARVORE_KG_ANO  # mesma base da metodologia
total_passagens = int(df["passagens"].sum())
qtd_perfis = contar_perfis()

c1, c2, c3, c4 = st.columns(4)
c1.metric("CO₂e evitado", f"{total_co2:,.1f} kg")
c2.metric("Equivale a", f"{arvores:,.1f} árvores/ano")
c3.metric("Perfis cadastrados", f"{qtd_perfis}")
c4.metric("Passagens de pedágio", f"{total_passagens}")

st.divider()


# =============================================================================
# 2) CALCULADORA INTERATIVA  (replica os inputs do cadastro.py)
# =============================================================================
st.subheader("🧮 Calculadora de emissões")
st.caption("Mesmos parâmetros do cadastro, agora em widgets web.")

col_in, col_out = st.columns([1, 1])
with col_in:
    veiculo_calc = st.selectbox(
        "Tipo de veículo", list(CONSUMO_EXTRA_POR_EVENTO.keys())
    )
    combustivel_calc = st.selectbox(
        "Combustível", list(FATOR_EMISSAO_COMBUSTIVEL.keys())
    )
    passagens_calc = st.number_input(
        "Passagens de pedágio com Taggy", min_value=0, value=20, step=1
    )
    estac_calc = st.number_input(
        "Usos de estacionamento com Taggy", min_value=0, value=8, step=1
    )

# Chama a funcao REAL de calculo
resultado_calc = calcular_total(
    passagens=int(passagens_calc),
    usos_estacionamento=int(estac_calc),
    tipo_veiculo=veiculo_calc,
    combustivel=combustivel_calc,
)

with col_out:
    st.metric("CO₂e total evitado", f"{resultado_calc['co2e_total_kg']} kg")
    st.write(f"- Pedágios: **{resultado_calc['co2e_pedagio_kg']} kg**")
    st.write(f"- Estacionamentos: **{resultado_calc['co2e_estacionamento_kg']} kg**")
    st.write(f"- Equivale a **{resultado_calc['equivalente_arvores']} árvore(s)/ano**")

st.divider()


# =============================================================================
# 3) MAPA DE CALOR DE RECIFE + RANKING DE BAIRROS
# =============================================================================
st.subheader("🗺️ Impacto por bairro em Recife")

# CO2e somado por bairro (base tanto do mapa quanto do ranking)
por_bairro = (
    df.groupby("bairro")["co2e_total_kg"].sum().reset_index()
    .sort_values("co2e_total_kg", ascending=False)
)

# CO2e por bairro JA normalizado — chave de cruzamento com o EBAIRRNOMEOF
co2_por_norm = (
    df.assign(_chave=df["bairro"].map(norm_bairro))
    .groupby("_chave")["co2e_total_kg"].sum()
    .to_dict()
)

col_mapa, col_rank = st.columns([1.4, 1])

with col_mapa:
    try:
        # --- Mapa coroplético com os polígonos reais do geojson ---
        geo = carregar_geojson()
        max_co2 = max(co2_por_norm.values()) if co2_por_norm else 0.0

        feats = []
        nomes_geo = set()
        for f in geo["features"]:
            nome_of = f["properties"].get("EBAIRRNOMEOF", "")
            chave = norm_bairro(nome_of)
            nomes_geo.add(chave)
            co2 = co2_por_norm.get(chave, 0.0)
            t = (co2 / max_co2) if max_co2 else 0.0  # intensidade 0..1

            if co2 > 0:
                # Escala YlGn: amarelo claro (pouco) -> verde escuro (muito)
                cor = [
                    int(255 + (0 - 255) * t),    # R
                    int(255 + (104 - 255) * t),  # G
                    int(204 + (55 - 204) * t),   # B
                    190,
                ]
            else:
                cor = [235, 235, 235, 60]        # cinza = bairro sem dados

            # Campos no topo da feature (top-level) garantem o tooltip do pydeck;
            # fill_color em properties é lido pelo accessor get_fill_color.
            feats.append({
                "type": "Feature",
                "geometry": f["geometry"],
                "bairro": nome_of,
                "co2e": round(co2, 2),
                "properties": {"fill_color": cor},
            })

        geo_render = {"type": "FeatureCollection", "features": feats}

        camada = pdk.Layer(
            "GeoJsonLayer",
            data=geo_render,
            get_fill_color="properties.fill_color",
            get_line_color=[120, 120, 120],
            line_width_min_pixels=0.5,
            stroked=True,
            filled=True,
            pickable=True,
        )
        view = pdk.ViewState(latitude=-8.05, longitude=-34.92, zoom=11.0)
        st.pydeck_chart(
            pdk.Deck(
                layers=[camada],
                initial_view_state=view,
                map_style="light",
                tooltip={"text": "{bairro}\nCO₂e evitado: {co2e} kg"},
            )
        )
        st.caption("Tom mais escuro = mais CO₂e evitado. Cinza = sem registros.")

        # Aviso (sem quebrar): bairros do banco que nao casaram com o geojson
        sem_match = sorted(
            {b for b in df["bairro"].unique() if norm_bairro(b) not in nomes_geo}
        )
        if sem_match:
            st.warning(
                "Bairros sem polígono no mapa (aparecem só no ranking ao lado): "
                + ", ".join(sem_match)
            )

    except Exception as e:
        # --- FALLBACK: dicionario hardcoded de coordenadas (pontos) ---
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
    rank = por_bairro.set_index("bairro")["co2e_total_kg"]
    st.bar_chart(rank)

st.divider()


# =============================================================================
# 4) GRAFICOS GERAIS
# =============================================================================
st.subheader("📊 Visão geral das emissões evitadas")
g1, g2, g3 = st.columns(3)

with g1:
    st.caption("Por tipo de veículo")
    por_veiculo = df.groupby("tipo_veiculo")["co2e_total_kg"].sum()
    st.bar_chart(por_veiculo)

with g2:
    st.caption("Por combustível")
    por_combustivel = df.groupby("combustivel")["co2e_total_kg"].sum()
    st.bar_chart(por_combustivel)

with g3:
    st.caption("Pedágio vs. Estacionamento")
    comparacao = pd.Series(
        {
            "pedágio": df["co2e_pedagio_kg"].sum(),
            "estacionamento": df["co2e_estac_kg"].sum(),
        }
    )
    st.bar_chart(comparacao)

st.divider()


# =============================================================================
# 5) RELATORIO AUDITAVEL (CSV) — funcionalidade ESG do projeto
# =============================================================================
st.subheader("📄 Relatório auditável (ESG)")
st.caption("Exporta os dados consolidados para auditoria de carbono evitado.")

# Resumo por bairro (consolidado)
resumo_bairro = (
    df.groupby("bairro")
    .agg(
        registros=("co2e_total_kg", "count"),
        passagens=("passagens", "sum"),
        estacionamentos=("estacionamentos", "sum"),
        co2e_total_kg=("co2e_total_kg", "sum"),
    )
    .reset_index()
    .sort_values("co2e_total_kg", ascending=False)
)

col_r1, col_r2 = st.columns(2)
with col_r1:
    st.download_button(
        "⬇️ Baixar relatório completo (CSV)",
        data=df.to_csv(index=False).encode("utf-8-sig"),
        file_name="heatcarbon_registros.csv",
        mime="text/csv",
        use_container_width=True,
    )
with col_r2:
    st.download_button(
        "⬇️ Baixar consolidado por bairro (CSV)",
        data=resumo_bairro.to_csv(index=False).encode("utf-8-sig"),
        file_name="heatcarbon_por_bairro.csv",
        mime="text/csv",
        use_container_width=True,
    )

with st.expander("Ver dados brutos (auditoria)"):
    st.dataframe(df, use_container_width=True)
