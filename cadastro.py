# cadastro.py — Registro de uso da Taggy pelo usuário
# Projeto: Heat Carbon | Projetos 2 — Cesar School


import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)
os.chdir(BASE_DIR)

from metodologia import calcular_total, CONSUMO_EXTRA_POR_EVENTO, FATOR_EMISSAO_COMBUSTIVEL
from banco import inserir_perfil, inserir_registro


# OPÇÕES DISPONÍVEIS


VEICULOS = {
    "1": "carro_leve",
    "2": "suv_caminhonete",
    "3": "moto",
    "4": "caminhao",
}

COMBUSTIVEIS = {
    "1": "gasolina",
    "2": "etanol",
    "3": "flex",
    "4": "diesel",
    "5": "eletrico",
}

# FUNÇÕES AUXILIARES


def perguntar_inteiro(mensagem, minimo=0):
    while True:
        try:
            valor = int(input(mensagem))
            if valor < minimo:
                print(f"  Digite um número maior ou igual a {minimo}.")
                continue
            return valor
        except ValueError:
            print("  Digite apenas números inteiros.")


def perguntar_opcao(mensagem, opcoes: dict):
    while True:
        print(mensagem)
        for chave, valor in opcoes.items():
            print(f"  {chave} - {valor}")
        escolha = input("Escolha: ").strip()
        if escolha in opcoes:
            return opcoes[escolha]
        print("  Opção inválida. Tente novamente.")



# FLUXO DE CADASTRO


def main():
    print("\n========================================")
    print("        🌿 Heat Carbon — Cadastro")
    print("========================================\n")

    # Perfil
    nome = input("Seu nome (ou Enter para Anônimo): ").strip() or "Anônimo"
    bairro = input("Seu bairro em Recife: ").strip()

    tipo_veiculo = perguntar_opcao(
        "\nTipo de veículo:",
        {"1": "carro_leve", "2": "suv_caminhonete", "3": "moto", "4": "caminhao"},
    )

    combustivel = perguntar_opcao(
        "\nCombustível:",
        {"1": "gasolina", "2": "etanol", "3": "flex", "4": "diesel", "5": "eletrico"},
    )

    # Uso mensal
    print("\n--- Uso este mês ---")
    passagens       = perguntar_inteiro("Passagens de pedágio com Taggy: ", minimo=0)
    estacionamentos = perguntar_inteiro("Usos de estacionamento com Taggy: ", minimo=0)

    # Cálculo
    resultado = calcular_total(
        passagens=passagens,
        usos_estacionamento=estacionamentos,
        tipo_veiculo=tipo_veiculo,
        combustivel=combustivel,
    )

    # Salva no banco
    pid = inserir_perfil(nome, bairro, tipo_veiculo, combustivel)
    inserir_registro(
        perfil_id=pid,
        passagens=passagens,
        estacionamentos=estacionamentos,
        co2e_pedagio_kg=resultado["co2e_pedagio_kg"],
        co2e_estac_kg=resultado["co2e_estacionamento_kg"],
        co2e_total_kg=resultado["co2e_total_kg"],
    )

    # Resultado
    print("\n========================================")
    print("           ✅ Cadastro salvo!           ")
    print("========================================")
    print(f"  CO₂e evitado em pedágios:        {resultado['co2e_pedagio_kg']} kg")
    print(f"  CO₂e evitado em estacionamentos: {resultado['co2e_estacionamento_kg']} kg")
    print(f"  Total CO₂e evitado:              {resultado['co2e_total_kg']} kg")
    print(f"  Equivale a plantar:              {resultado['equivalente_arvores']} árvore(s)")
    print("========================================\n")


if __name__ == "__main__":
    main()
