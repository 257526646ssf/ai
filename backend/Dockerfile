FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    AITEST_DATABASE_URL=sqlite:///./data/aitest.sqlite3

WORKDIR /app/backend

COPY pyproject.toml ./pyproject.toml

RUN python -m pip install --upgrade pip \
    && python -c "from pathlib import Path; import tomllib; import subprocess; import sys; deps = tomllib.loads(Path('pyproject.toml').read_text(encoding='utf-8'))['project']['dependencies']; subprocess.check_call([sys.executable, '-m', 'pip', 'install', *deps])"

COPY aitest_platform ./aitest_platform

RUN mkdir -p /app/backend/data

EXPOSE 8000

CMD ["uvicorn", "aitest_platform.main:app", "--host", "0.0.0.0", "--port", "8000"]
