FROM apache/airflow:2.10.5-python3.12

USER airflow
RUN pip install --no-cache-dir "psycopg2-binary==2.9.9"

ENV AIRFLOW_HOME=/opt/airflow

COPY airflow/airflow.cfg /opt/airflow/airflow.cfg
