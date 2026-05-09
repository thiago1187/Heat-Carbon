
# banco.py — Banco de dados SQLite do projeto Heat Carbon
# Projeto: Projetos 2 — Cesar School


import sqlite3
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH  = os.path.join(BASE_DIR, "data", "taggy.db")


def conectar():
    return sqlite3.connect(DB_PATH)


def criar_tabelas():
    with conectar() as con:
        con.executescript("""
            CREATE TABLE IF NOT EXISTS perfil (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                nome          TEXT    NOT NULL,
                bairro        TEXT    NOT NULL,
                tipo_veiculo  TEXT    NOT NULL,
                combustivel   TEXT    NOT NULL,
                criado_em     DATETIME DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS registros (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                perfil_id         INTEGER NOT NULL REFERENCES perfil(id),
                passagens         INTEGER NOT NULL,
                estacionamentos   INTEGER NOT NULL,
                co2e_pedagio_kg   REAL    NOT NULL,
                co2e_estac_kg     REAL    NOT NULL,
                co2e_total_kg     REAL    NOT NULL,
                registrado_em     DATETIME DEFAULT CURRENT_TIMESTAMP
            );
        """)


def inserir_perfil(nome, bairro, tipo_veiculo, combustivel):
    with conectar() as con:
        cursor = con.execute(
            "INSERT INTO perfil (nome, bairro, tipo_veiculo, combustivel) VALUES (?, ?, ?, ?)",
            (nome, bairro, tipo_veiculo, combustivel),
        )
        return cursor.lastrowid


def inserir_registro(perfil_id, passagens, estacionamentos, co2e_pedagio_kg, co2e_estac_kg, co2e_total_kg):
    with conectar() as con:
        con.execute(
            """INSERT INTO registros
               (perfil_id, passagens, estacionamentos, co2e_pedagio_kg, co2e_estac_kg, co2e_total_kg)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (perfil_id, passagens, estacionamentos, co2e_pedagio_kg, co2e_estac_kg, co2e_total_kg),
        )


def carregar_dados():
    """Retorna todos os registros com os dados de perfil — usado no notebook."""
    import pandas as pd
    query = """
        SELECT
            p.nome, p.bairro, p.tipo_veiculo, p.combustivel,
            r.passagens, r.estacionamentos,
            r.co2e_pedagio_kg, r.co2e_estac_kg, r.co2e_total_kg,
            r.registrado_em
        FROM registros r
        JOIN perfil p ON r.perfil_id = p.id
    """
    with conectar() as con:
        return pd.read_sql_query(query, con)


# Garante que as tabelas existem ao importar
criar_tabelas()
