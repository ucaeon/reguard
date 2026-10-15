ARG JDK=eclipse-temurin:21-jdk@sha256:f9bf7e9fe2f9bc4657537c1a7e20c768f0c3bafca41598263be4714783dd62eb
ARG JRE=eclipse-temurin:21-jre@sha256:ccbad9e7cb84c27092b12c40a4143e5733e050db9c3784d84f632dcf423fb2ef
FROM ${JDK} AS build
WORKDIR /build
COPY .mvn .mvn
COPY mvnw pom.xml ./
COPY services services
COPY infra/runtime/Healthcheck.java ./
RUN javac Healthcheck.java
ARG SERVICE
RUN chmod +x mvnw && ./mvnw -B -ntp -pl services/${SERVICE} -am package -DskipTests && cp services/${SERVICE}/target/${SERVICE}-0.0.1-SNAPSHOT.jar /app.jar

FROM ${JRE}
WORKDIR /app
COPY --from=build /app.jar app.jar
COPY --from=build /build/Healthcheck.class ./
USER 10001:10001
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 CMD ["java","-Xmx32m","-cp","/app","Healthcheck"]
ENTRYPOINT ["java","-XX:MaxRAMPercentage=70","-jar","app.jar"]
