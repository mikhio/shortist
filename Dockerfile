FROM python:3.12-slim

COPY ./requirements.txt /app/requirements.txt

WORKDIR /app
RUN pip install --no-cache-dir -r requirements.txt

COPY . /app

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]