FROM eclipse-temurin:21-jre AS java
FROM python:3.12.14-slim-bookworm
COPY --from=java /opt/java/openjdk /opt/java/openjdk
ENV JAVA_HOME=/opt/java/openjdk
ENV PATH=/opt/java/openjdk/bin:$PATH
ENV PYTHONPATH=/opt/reguard
ENV SPARK_LOCAL_IP=127.0.0.1
RUN pip install --no-cache-dir pyspark==4.0.3 "psycopg[binary]==3.2.10" python-dotenv==1.1.1
WORKDIR /opt/reguard
ENTRYPOINT ["python", "-m", "pipelines.spark.streaming_job"]
CMD ["--checkpoint", "/checkpoints/safety-raw-v1"]
