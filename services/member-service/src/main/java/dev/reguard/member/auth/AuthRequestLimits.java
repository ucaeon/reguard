package dev.reguard.member.auth;

import dev.reguard.member.api.ApiException;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;
import java.util.Map;

@Service
public class AuthRequestLimits {
    private final NamedParameterJdbcTemplate jdbc;

    public AuthRequestLimits(NamedParameterJdbcTemplate jdbc) { this.jdbc = jdbc; }

    // Commit attempts even when the enclosing authentication transaction fails.
    @Transactional(propagation = Propagation.REQUIRES_NEW, noRollbackFor = ApiException.class)
    public void acquire(String scope, String identity, int maximum, int seconds) {
        String key = SignupVerification.hash(scope + ":" + identity);
        var accepted = jdbc.queryForList("""
            INSERT INTO auth_request_limits(bucket_hash,attempts,expires_at)
            VALUES (:key,1,clock_timestamp()+make_interval(secs => :seconds))
            ON CONFLICT(bucket_hash) DO UPDATE SET
              attempts=CASE WHEN auth_request_limits.expires_at<=clock_timestamp()
                            THEN 1 ELSE auth_request_limits.attempts+1 END,
              expires_at=CASE WHEN auth_request_limits.expires_at<=clock_timestamp()
                             THEN clock_timestamp()+make_interval(secs => :seconds)
                             ELSE auth_request_limits.expires_at END
            WHERE auth_request_limits.expires_at<=clock_timestamp()
               OR auth_request_limits.attempts<:maximum
            RETURNING attempts
            """, Map.of("key",key,"maximum",maximum,"seconds",seconds), Integer.class);
        if (accepted.isEmpty()) throw new ApiException(429,"TOO_MANY_REQUESTS","요청이 많습니다. 잠시 후 다시 시도해 주세요.");
    }

    @Scheduled(fixedDelay = 3600000)
    public void cleanup() {
        jdbc.update("DELETE FROM auth_request_limits WHERE expires_at<clock_timestamp()", Map.of());
    }
}
