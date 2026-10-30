"""Caminhos e parâmetros globais do case."""
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
DADOS_BRUTOS = RAIZ / "data" / "raw"          # extração "SAP" (CSV, tudo texto)
DADOS_PROC = RAIZ / "data" / "processed"      # warehouse DuckDB + previsões
SQL_DIR = RAIZ / "sql"                         # camada semântica
RELATORIOS = RAIZ / "reports"
FIGURAS = RELATORIOS / "figures"

SEMENTE = 42
HORIZONTE = 4            # semanas: lead time de reposição coberto pela previsão
QUANTIL = 0.90           # quantil do modelo usado como medida de incerteza
NIVEL_SERVICO = 0.95     # atendimento-alvo: % do valor demandado servido na hora
PASSO_RETREINO = 13      # retreina o modelo a cada trimestre no backtest

# Janelas do backtest (semana de origem; semana 0 = 06/07/2020, início da safra 20/21)
CALIBRACAO = (207, 258)  # origens cujo alvo começa na safra 24/25
TESTE = (259, 307)       # origens cujo alvo cai na safra 25/26
