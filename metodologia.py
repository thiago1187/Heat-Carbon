# Calculadora de emissões evitadas pelo uso da Taggy
# Projeto: Heat Carbon | Projetos 2 — Cesar School
#


# TABELAS DE REFERÊNCIA

# (Feito por Vini)
# Lógica: sem taggy, o veículo desacelera, para/fica em marcha lenta
# e acelera novamente — esse ciclo consome combustível extra.
CONSUMO_EXTRA_POR_EVENTO = {
    "carro_leve":      0.15,   # ex: Gol, HB20, Onix
    "suv_caminhonete": 0.20,   # ex: Compass, Hilux, Tracker
    "moto":            0.06,   # ex: CG 160, XRE 300
    "caminhao":        0.35,   # veículo pesado / frete
}

# Fator de emissão por combustível (kgCO2e por litro)  Fonte: CETESB 2023

FATOR_EMISSAO_COMBUSTIVEL = {
    "gasolina": 2.27,
    "etanol":   1.61,
    "flex":     1.94,   # média ponderada 50% gasolina / 50% etanol
    "diesel":   2.66,
    "eletrico": 0.00,   # emissão direta zero (escopo 1)
}

# CO2e evitado por ticket de papel de estacionamento não impresso (em kg)
# Base: ticket térmico ~5g de papel; produção de papel ~1,0 kgCO2e/kg
CO2E_POR_TICKET_PAPEL = 0.005

# Absorção média anual de CO2 por árvore  (em kg/ano) Fonte: IPCC AR6 — média espécies tropicais brasileiras
ABSORCAO_ARVORE_KG_ANO = 21.77



# FUNÇÕES DE CÁLCULO


def calcular_co2e_pedagio(passagens: int, tipo_veiculo: str, combustivel: str) -> float:
    """
    Calcula o CO2e evitado pelo uso da Taggy em passagens de pedágio.

    Parâmetros:
        passagens    : número de passagens de pedágio com Taggy no período
        tipo_veiculo : chave do dicionário CONSUMO_EXTRA_POR_EVENTO
        combustivel  : chave do dicionário FATOR_EMISSAO_COMBUSTIVEL

    Retorna:
        CO2e evitado em kg (float)
    """
    consumo = CONSUMO_EXTRA_POR_EVENTO[tipo_veiculo]
    fator   = FATOR_EMISSAO_COMBUSTIVEL[combustivel]
    return passagens * consumo * fator


def calcular_co2e_estacionamento(usos: int) -> float:
    """
    Calcula o CO2e evitado por não utilizar tickets de papel no estacionamento.

    Parâmetros:
        usos : número de entradas em estacionamento com Taggy no período

    Retorna:
        CO2e evitado em kg (float)
    """
    return usos * CO2E_POR_TICKET_PAPEL


def calcular_total(
    passagens: int,
    usos_estacionamento: int,
    tipo_veiculo: str,
    combustivel: str
) -> dict:
    """
    Cálculo completo de CO2e evitado pelo uso da Taggy em um período.

    Retorna dicionário com:
        co2e_pedagio_kg        : emissão evitada pelos pedágios (kg)
        co2e_estacionamento_kg : emissão evitada pelos estacionamentos (kg)
        co2e_total_kg          : total evitado (kg)
        equivalente_arvores    : quantas árvores precisariam de 1 ano para
                                 absorver esse CO2 equivalente
    """
    co2_pedagio = calcular_co2e_pedagio(passagens, tipo_veiculo, combustivel)
    co2_estac   = calcular_co2e_estacionamento(usos_estacionamento)
    total       = co2_pedagio + co2_estac

    return {
        "co2e_pedagio_kg":        round(co2_pedagio, 3),
        "co2e_estacionamento_kg": round(co2_estac, 3),
        "co2e_total_kg":          round(total, 3),
        "equivalente_arvores":    round(total / ABSORCAO_ARVORE_KG_ANO, 2),
    }



# TESTE RÁPIDO

if __name__ == "__main__":
    # Exemplo: usuário com carro flex, 20 pedágios e 8 estacionamentos no mês
    resultado = calcular_total(
        passagens=20,
        usos_estacionamento=8,
        tipo_veiculo="carro_leve",
        combustivel="flex"
    )

    print("=== Resultado do cálculo ===")
    print(f"CO2e evitado em pedágios:        {resultado['co2e_pedagio_kg']} kg")
    print(f"CO2e evitado em estacionamentos: {resultado['co2e_estacionamento_kg']} kg")
    print(f"Total CO2e evitado:              {resultado['co2e_total_kg']} kg")
    print(f"Equivalente a:                   {resultado['equivalente_arvores']} árvores/ano")
