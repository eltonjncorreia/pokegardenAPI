.PHONY: install test eval eval-live run clean

PYTHON ?= python3.12
VENV := .venv/bin
STAMP := .venv/.installed

## install: cria o .venv e instala as dependências (refaz se requirements.txt mudar)
install: $(STAMP)

$(STAMP): requirements.txt
	test -d .venv || $(PYTHON) -m venv .venv
	$(VENV)/pip install --upgrade pip
	$(VENV)/pip install -r requirements.txt
	touch $(STAMP)

## clean: remove caches do Python e de testes
clean:
	find . -path ./.venv -prune -o -type d -name '__pycache__' -prune -exec rm -rf {} +
	find . -type f -name '*.py[cod]' -not -path './.venv/*' -delete
	rm -rf .pytest_cache .mypy_cache .ruff_cache

## test: limpa caches e roda a suíte de testes
test: install clean
	$(VENV)/pytest

## eval: avaliação offline (pytest + agente com modelo roteirizado), relatório em evidence/evals/
eval: install clean
	$(VENV)/python -m evals.run --mode offline

## eval-live: avaliação com o modelo real e a PokéAPI real (requer OPENAI_API_KEY)
eval-live: install clean
	$(VENV)/python -m evals.run --mode live

## run: cria o .venv, instala as dependências e sobe o servidor FastAPI
run: install clean
	$(VENV)/uvicorn --app-dir src main:app --reload
