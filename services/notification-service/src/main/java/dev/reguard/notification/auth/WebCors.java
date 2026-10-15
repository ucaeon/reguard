package dev.reguard.notification.auth;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.*;
import org.springframework.web.cors.*;

import java.util.*;

@Configuration
public class WebCors {
    @Bean
    CorsConfigurationSource corsConfigurationSource(
            @Value("${reguard.web.allowed-origins:http://localhost:3000,http://127.0.0.1:3000}")
                    String origins) {
        var allowed =
                Arrays.stream(origins.split(","))
                        .map(String::strip)
                        .filter(s -> !s.isEmpty())
                        .toList();

        if (allowed.stream().anyMatch(s -> s.contains("*")))
            throw new IllegalArgumentException("Explicit web origins required");
        var config = new CorsConfiguration();
        config.setAllowedOrigins(allowed);
        config.setAllowCredentials(true);
        config.setAllowedMethods(List.of("GET", "POST", "PATCH", "DELETE", "OPTIONS"));
        config.setAllowedHeaders(List.of("Content-Type", "X-XSRF-TOKEN", "Authorization"));
        config.setMaxAge(600L);
        var source = new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", config);

        return source;
    }
}
