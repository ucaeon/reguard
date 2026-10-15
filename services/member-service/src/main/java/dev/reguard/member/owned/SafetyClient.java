package dev.reguard.member.owned;

import com.fasterxml.jackson.databind.JsonNode;

import dev.reguard.member.api.ApiException;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.client.JdkClientHttpRequestFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.client.*;

import java.net.http.HttpClient;
import java.time.Duration;
import java.util.UUID;

@Component
public class SafetyClient {
    private final RestClient client;

    public SafetyClient(@Value("${reguard.safety-base-url:http://127.0.0.1:8082}") String baseUrl) {
        var factory =
                new JdkClientHttpRequestFactory(
                        HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(2)).build());
        factory.setReadTimeout(Duration.ofSeconds(5));
        client = RestClient.builder().baseUrl(baseUrl).requestFactory(factory).build();
    }

    public JsonNode product(UUID id) {
        var body = get("/api/v1/products/" + id);

        if (!id.toString().equals(body.path("id").asText())
                || !body.path("name").isTextual()
                || body.path("name").asText().isBlank()) throw unavailable();

        return body;
    }

    public JsonNode recalls(UUID id, int page, int size) {
        var body = get("/api/v1/products/" + id + "/recalls?page=" + page + "&size=" + size);

        if (!body.path("items").isArray() || !body.path("hasNext").isBoolean()) {
            throw unavailable();
        }
        return body;
    }

    public JsonNode recalls(OwnedProduct product, int page, int size) {
        if (product.catalogProductId() != null) return recalls(product.catalogProductId(), page, size);
        var query = new java.util.HashMap<String, Object>();
        query.put("productName", product.productName());
        query.put("companyName", product.companyName());
        query.put("modelName", product.modelName());
        query.put("identifierType", product.identifierType());
        query.put("identifierValue", product.identifierValue());
        try {
            var body = client.post().uri("/api/v1/recalls/match?page=" + page + "&size=" + size)
                    .body(query).retrieve().body(JsonNode.class);
            if (body == null || !body.path("items").isArray() || !body.path("hasNext").isBoolean())
                throw unavailable();
            return body;
        } catch (RestClientException e) {
            throw unavailable();
        }
    }

    private JsonNode get(String path) {
        try {
            JsonNode body = client.get().uri(path).retrieve().body(JsonNode.class);

            if (body == null || !body.isObject()) {
                throw unavailable();
            }
            return body;
        } catch (HttpClientErrorException.NotFound e) {
            throw new ApiException(404, "CATALOG_PRODUCT_NOT_FOUND", "연결할 제품을 찾을 수 없습니다.");
        } catch (RestClientException e) {
            throw unavailable();
        }
    }

    private ApiException unavailable() {
        return new ApiException(503, "SAFETY_UNAVAILABLE", "제품·리콜 서버에 일시적으로 연결할 수 없습니다.");
    }
}
