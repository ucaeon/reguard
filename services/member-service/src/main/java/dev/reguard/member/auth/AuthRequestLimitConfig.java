package dev.reguard.member.auth;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.HandlerInterceptor;
import org.springframework.web.servlet.config.annotation.InterceptorRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class AuthRequestLimitConfig implements WebMvcConfigurer {
    private final AuthRequestLimits limits;
    public AuthRequestLimitConfig(AuthRequestLimits limits) { this.limits = limits; }
    @Override
    public void addInterceptors(InterceptorRegistry registry) {
        registry.addInterceptor(new HandlerInterceptor() {
            @Override
            public boolean preHandle(HttpServletRequest request, HttpServletResponse response, Object handler) {
                if ("POST".equals(request.getMethod())) {
                    limits.acquire("auth-ip", request.getRemoteAddr(), 60, 60);
                }
                return true;
            }
        }).addPathPatterns("/api/v1/auth/**").excludePathPatterns("/api/v1/auth/logout");
    }
}
