ARG AIRFLOW
FROM ${AIRFLOW}
RUN pip install --no-cache-dir "apache-airflow==3.1.8" "confluent-kafka==2.6.1" "psycopg[binary]==3.2.10" "python-dotenv==1.1.1" "ijson==3.4.0" && pip check
ENV PYTHONPATH=/opt/reguard

COPY --chown=50000:0 orchestration /opt/reguard/orchestration
COPY --chown=50000:0 pipelines /opt/reguard/pipelines
COPY --chown=50000:0 scripts /opt/reguard/scripts
COPY --chown=50000:0 orchestration/airflow/dags /opt/airflow/dags
