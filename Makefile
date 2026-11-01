PY := .venv/bin/python
export PYTHONPATH := src

.PHONY: all setup run test clean

all: setup run test

setup:
	@test -d .venv || python3 -m venv .venv
	@.venv/bin/pip install -q -r requirements.txt

run:
	$(PY) -m rm.outputs

test:
	$(PY) -m pytest -q

clean:
	rm -f output/*.csv
