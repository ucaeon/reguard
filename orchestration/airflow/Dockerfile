FROM apache/airflow:3.1.8-python3.12
RUN pip install --no-cache-dir "apache-airflow==3.1.8" "confluent-kafka==2.6.1" "psycopg[binary]==3.2.10" "python-dotenv==1.1.1" "ijson==3.4.0" && pip check
ENV PYTHONPATH=/opt/reguard
