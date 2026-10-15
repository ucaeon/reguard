package dev.reguard.member.auth;

import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpServletResponse;

import java.time.OffsetDateTime;

class LoginCookiesTest {
    @Test
    void httpsCookieUsesHostPrefixAndCannotBeReadByJavascript() {
        var response = new MockHttpServletResponse();
        new LoginCookies(true)
                .issue(
                        response,
                        new AuthService.Token(
                                "test-token", "Bearer", OffsetDateTime.now().plusHours(24)));
        String value = response.getHeader("Set-Cookie");
        assertTrue(value.startsWith("__Host-REGUARD_SESSION="));
        assertTrue(value.contains("Secure"));
        assertTrue(value.contains("HttpOnly"));
        assertTrue(value.contains("SameSite=Lax"));
        assertTrue(value.contains("Path=/"));
        assertFalse(value.contains("Domain="));
    }

    @Test
    void logoutExpiresTheSameCookieNamesAndScope() {
        var response = new MockHttpServletResponse();
        new LoginCookies(true).clear(response);
        assertEquals(3, response.getHeaders("Set-Cookie").size());

        for (String cookie : response.getHeaders("Set-Cookie")) {
            assertTrue(cookie.startsWith("__Host-REGUARD_"));
            assertTrue(cookie.contains("Max-Age=0"));
            assertTrue(cookie.contains("Path=/"));
        }
    }
}
