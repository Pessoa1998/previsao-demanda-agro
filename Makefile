PY ?= python
export PYTHONPATH := src
NOTEBOOK := notebooks/case_previsao_demanda.ipynb

.PHONY: dados pipeline testes notebook tudo limpar

dados:          ## gera a extração SAP sintética em data/raw
	$(PY) -m demanda.gerar_dados

pipeline: dados ## camada SQL, backtest, métricas, figuras e recomendação
	$(PY) -m demanda.pipeline

testes:         ## testes automatizados (dados, SQL, vazamento, métricas)
	$(PY) -m pytest -q

notebook:       ## reexecuta o notebook (requer: pip install nbclient ipykernel)
	$(PY) -c "import nbformat; from nbclient import NotebookClient; \
	nb = nbformat.read('$(NOTEBOOK)', as_version=4); \
	NotebookClient(nb, timeout=1800, resources={'metadata': {'path': 'notebooks'}}).execute(); \
	nbformat.write(nb, '$(NOTEBOOK)')"

tudo: testes pipeline

limpar:
	rm -rf data/raw data/processed
