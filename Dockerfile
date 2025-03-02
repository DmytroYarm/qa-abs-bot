FROM python:3.13-slim


WORKDIR /app


COPY poetry.lock pyproject.toml ./


RUN pip install poetry
RUN poetry config virtualenvs.create false \
    && poetry install --no-interaction --no-ansi


COPY . .


CMD ["python", "main.py"]