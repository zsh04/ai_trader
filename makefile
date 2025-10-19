dev:
\tpython -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt

run:
\tuvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

dashboard:
\tstreamlit run app/monitoring/dashboard.py

test:
\tpytest -v

lint:
\truff check .

deploy:
\tgh workflow run Deploy-Azure-AppService