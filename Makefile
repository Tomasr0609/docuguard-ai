.PHONY: install run run-api run-frontend seed eval test clean

install:
	python -m venv .venv
	.venv/bin/pip install -r requirements.txt

run:
	.venv/bin/uvicorn backend.api.main:app --reload --port 8000 &
	.venv/bin/streamlit run app.py

run-api:
	.venv/bin/uvicorn backend.api.main:app --reload --port 8000

run-frontend:
	.venv/bin/streamlit run app.py

seed:
	.venv/bin/python scripts/seed_corpus.py

eval:
	.venv/bin/python eval/run_eval.py

test:
	.venv/bin/python -m pytest tests/ -v

clean:
	rm -rf chroma_db/ logs/ docuguard.db data/uploads/
