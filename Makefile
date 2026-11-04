export PYTHONPATH := src

ifeq ($(OS),Windows_NT)
# Windows: the venv lives outside the repo so a synced folder (OneDrive)
# does not mix it with a macOS .venv. Needs uv (https://docs.astral.sh/uv/).
SHELL := cmd.exe
VENV ?= $(LOCALAPPDATA)\venvs\ktg-northline-rm
PY := "$(VENV)\Scripts\python.exe"
else
VENV ?= .venv
PY := $(VENV)/bin/python
endif

.PHONY: all setup run test clean

all: setup run test

ifeq ($(OS),Windows_NT)
setup:
	@if not exist $(PY) uv venv -q --python 3.11 "$(VENV)"
	@uv pip install -q --python $(PY) -r requirements.txt
else
setup:
	@test -d $(VENV) || python3 -m venv $(VENV)
	@$(VENV)/bin/pip install -q -r requirements.txt
endif

run:
	$(PY) -m rm.outputs

test:
	$(PY) -m pytest -q

ifeq ($(OS),Windows_NT)
clean:
	@if exist output\*.csv del /q output\*.csv
else
clean:
	rm -f output/*.csv
endif
