package dev.reguard.notification.auth;

import com.fasterxml.jackson.databind.JsonNode;

import dev.reguard.notification.api.ApiException;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.client.JdkClientHttpRequestFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.client.*;

import java.net.http.HttpClient;
import java.time.Duration;
import java.util.UUID;

@Component
public class MemberIdentityClient {
    private final RestClient client;

    public MemberIdentityClient(
            @Value("${reguard.member-base-url:http://127.0.0.1:8081}") String url) {
        var factory =
                new JdkClientHttpRequestFactory(
                        HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(2)).build());
        factory.setReadTimeout(Duration.ofSeconds(3));
        client = RestClient.builder().baseUrl(url).requestFactory(factory).build();
    }

    public UUID authenticate(String token) {
        if (!token.matches("[A-Za-z0-9_-]{43}")) {
            return null;
        }
        try {
            var body =
                    client.get()
                            .uri("/api/v1/me")
                            .header("Authorization", "Bearer " + token)
                            .retrieve()
                            .body(JsonNode.class);

            if (body == null) {
                throw new IllegalArgumentException();
            }
            return UUID.fromString(body.path("id").asText());
        } catch (HttpClientErrorException.Unauthorized e) {
            return null;
        } catch (RestClientException | IllegalArgumentException e) {
            throw new ApiException(503, "AUTH_UNAVAILABLE", "로그인 서버에 일시적으로 연결할 수 없습니다.");
        }
    }
}
