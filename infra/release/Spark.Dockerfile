ARG JRE
ARG PYTHON
FROM ${JRE} AS java
FROM ${PYTHON}
COPY --from=java /opt/java/openjdk /opt/java/openjdk
ENV JAVA_HOME=/opt/java/openjdk
ENV PATH=/opt/java/openjdk/bin:$PATH
ENV PYTHONPATH=/opt/reguard
ENV SPARK_LOCAL_IP=127.0.0.1
RUN pip install --no-cache-dir pyspark==4.0.3 "psycopg[binary]==3.2.10" python-dotenv==1.1.1
WORKDIR /opt/reguard
ENTRYPOINT ["python", "-m", "pipelines.spark.streaming_job"]
CMD ["--checkpoint", "/checkpoints/safety-raw-v1"]

RUN python -c "from pyspark.sql import SparkSession; s=SparkSession.builder.master('local[1]').config('spark.jars.ivy','/tmp/ivy').config('spark.jars.packages','org.apache.spark:spark-sql-kafka-0-10_2.13:4.0.3').getOrCreate(); s.stop()" && mkdir -p /opt/kafka-jars && cp /tmp/ivy/jars/*.jar /opt/kafka-jars/ && rm -rf /tmp/ivy
ENV SPARK_KAFKA_JARS=/opt/kafka-jars
COPY pipelines /opt/reguard/pipelines
COPY scripts /opt/reguard/scripts
