package dev.reguard.member.auth;

import com.fasterxml.jackson.databind.ObjectMapper;

import dev.reguard.member.api.ApiErrors.ErrorBody;

import jakarta.servlet.*;
import jakarta.servlet.http.*;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.*;
import org.springframework.http.HttpMethod;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.csrf.*;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;
import java.util.*;

@Configuration
public class SecurityConfig {
    public static final String AUTH_TOKEN = "reguard.auth.token";
    public static final String AUTH_MODE = "reguard.auth.mode";
    private static final Set<String> SAFE_METHODS = Set.of("GET", "HEAD", "OPTIONS", "TRACE");
    private static final Set<String> PUBLIC_PATHS =
            Set.of(
                    "/api/v1/auth/csrf", "/api/v1/auth/signup",
                    "/api/v1/auth/login", "/api/v1/auth/token",
                    "/api/v1/auth/password-reset/request", "/api/v1/auth/password-reset/confirm", "/api/v1/auth/signup/email/request", "/api/v1/auth/signup/email/verify");

    @Bean
    org.springframework.security.crypto.password.PasswordEncoder passwordEncoder() {
        return new org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder();
    }

    @Bean
    CookieCsrfTokenRepository csrfTokens(@Value("${reguard.cookie.secure:false}") boolean secure) {
        var repository = new CookieCsrfTokenRepository();
        repository.setCookieName((secure ? "__Host-" : "") + "REGUARD_MEMBER_CSRF");
        repository.setCookiePath("/");
        repository.setCookieCustomizer(
                cookie -> cookie.httpOnly(true).secure(secure).sameSite("Lax"));

        return repository;
    }

    @Bean
    SecurityFilterChain security(
            HttpSecurity http,
            AuthService auth,
            ObjectMapper mapper,
            CookieCsrfTokenRepository csrfTokens,
            @Value("${reguard.cookie.secure:false}") boolean secure)
            throws Exception {
        String cookieName = (secure ? "__Host-" : "") + "REGUARD_SESSION";
        http.cors(org.springframework.security.config.Customizer.withDefaults())
                .csrf(
                        csrf ->
                                csrf.csrfTokenRepository(csrfTokens)
                                        .sessionAuthenticationStrategy(
                                                new org.springframework.security.web.authentication
                                                        .session.NullAuthenticatedSessionStrategy())
                                        .requireCsrfProtectionMatcher(
                                                req ->
                                                        !SAFE_METHODS.contains(req.getMethod())
                                                                && !"bearer"
                                                                        .equals(
                                                                                req.getAttribute(
                                                                                        AUTH_MODE))))
                .sessionManagement(s -> s.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
                .requestCache(c -> c.disable())
                .formLogin(c -> c.disable())
                .httpBasic(c -> c.disable())
                .logout(c -> c.disable())
                .authorizeHttpRequests(
                        a ->
                                a.requestMatchers(HttpMethod.GET, "/api/v1/auth/csrf")
                                        .permitAll()
                                        .requestMatchers(
                                                HttpMethod.POST,
                                                "/api/v1/auth/signup", "/api/v1/auth/login",
                                                "/api/v1/auth/token", "/api/v1/auth/password-reset/request",
                                                "/api/v1/auth/password-reset/confirm", "/api/v1/auth/signup/email/request", "/api/v1/auth/signup/email/verify")
                                        .permitAll()
                                        .requestMatchers("/actuator/health", "/actuator/health/**")
                                        .permitAll()
                                        .anyRequest()
                                        .authenticated())
                .exceptionHandling(
                        e ->
                                e.authenticationEntryPoint(
                                                (req, res, ex) ->
                                                        error(
                                                                res,
                                                                mapper,
                                                                401,
                                                                "UNAUTHORIZED", "로그인이 필요합니다."))
                                        .accessDeniedHandler(
                                                (req, res, ex) ->
                                                        error(
                                                                res,
                                                                mapper,
                                                                403,
                                                                ex instanceof CsrfException
                                                                        ? "CSRF_INVALID"
                                                                        : "FORBIDDEN",
                                                                ex instanceof CsrfException
                                                                        ? "요청 확인 토큰이 없거나 올바르지 않습니다."
                                                                        : "접근할 수 없습니다.")))
                .addFilterBefore(
                        new OncePerRequestFilter() {
                            @Override
                            protected void doFilterInternal(
                                    HttpServletRequest req,
                                    HttpServletResponse res,
                                    FilterChain chain)
                                    throws ServletException, IOException {
                                String header = req.getHeader("Authorization");
                                List<String> cookies = new ArrayList<>();

                                if (req.getCookies() != null)
                                    for (Cookie c : req.getCookies())
                                        if (c.getName().equals(cookieName))
                                            cookies.add(c.getValue());

                                if (cookies.size() > 1 || (header != null && !cookies.isEmpty())) {
                                    error(
                                            res,
                                            mapper,
                                            400,
                                            "AMBIGUOUS_CREDENTIALS", "쿠키와 Authorization 인증을 함께 보내지 마세요.");
                                    return;
                                }
                                String token =
                                        header != null && header.startsWith("Bearer ")
                                                ? header.substring(7)
                                                : cookies.isEmpty() ? null : cookies.getFirst();

                                if (header != null && token == null) {
                                    error(res, mapper, 401, "UNAUTHORIZED", "올바른 인증 형식이 필요합니다.");
                                    return;
                                }
                                if (token != null) {
                                    java.util.UUID id;
                                    try {
                                        id = auth.authenticate(token);
                                    } catch (org.springframework.dao.DataAccessException e) {
                                        error(
                                                res,
                                                mapper,
                                                503,
                                                "DEPENDENCY_UNAVAILABLE", "인증을 일시적으로 처리할 수 없습니다.");
                                        return;
                                    }
                                    if (id == null) {
                                        if (header != null
                                                || !PUBLIC_PATHS.contains(req.getRequestURI())) {
                                            error(
                                                    res,
                                                    mapper,
                                                    401,
                                                    "UNAUTHORIZED", "유효한 로그인이 필요합니다.");
                                            return;
                                        }
                                    } else {
                                        var context = SecurityContextHolder.createEmptyContext();
                                        context.setAuthentication(
                                                new UsernamePasswordAuthenticationToken(
                                                        id, null, List.of()));
                                        SecurityContextHolder.setContext(context);
                                        req.setAttribute(AUTH_TOKEN, token);
                                        req.setAttribute(
                                                AUTH_MODE, header == null ? "cookie" : "bearer");
                                    }
                                }
                                chain.doFilter(req, res);
                            }
                        },
                        CsrfFilter.class);

        return http.build();
    }

    private static void error(
            HttpServletResponse response,
            ObjectMapper mapper,
            int status,
            String code,
            String message)
            throws IOException {
        response.setStatus(status);
        response.setContentType("application/json");
        response.setCharacterEncoding("UTF-8");
        mapper.writeValue(response.getWriter(), new ErrorBody(code, message, List.of()));
    }
}
