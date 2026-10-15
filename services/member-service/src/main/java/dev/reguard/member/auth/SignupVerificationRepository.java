package dev.reguard.member.auth;

import java.util.List;
import java.util.Map;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class SignupVerificationRepository {
    private final NamedParameterJdbcTemplate jdbc;

    public SignupVerificationRepository(NamedParameterJdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public int issue(String email, String digest) {
        return jdbc.update("""
            INSERT INTO signup_email_verifications(email,code_hash,expires_at)
            VALUES (:email,:hash,CURRENT_TIMESTAMP + INTERVAL '10 minutes')
            ON CONFLICT(email) DO UPDATE SET code_hash=:hash, expires_at=CURRENT_TIMESTAMP + INTERVAL '10 minutes',
            sent_at=CURRENT_TIMESTAMP, attempts=0, proof_hash=NULL
            WHERE signup_email_verifications.sent_at < CURRENT_TIMESTAMP - INTERVAL '60 seconds'
            """, Map.of("email", email, "hash", digest));
    }

    public List<String> attempt(String email) {
        return jdbc.queryForList("""
            UPDATE signup_email_verifications SET attempts=attempts+1
            WHERE email=:email AND expires_at>CURRENT_TIMESTAMP AND attempts<5 AND proof_hash IS NULL
            RETURNING code_hash
            """, Map.of("email", email), String.class);
    }

    public int saveProof(String email, String digest, String proofHash) {
        return jdbc.update("""
            UPDATE signup_email_verifications SET proof_hash=:proof, expires_at=CURRENT_TIMESTAMP + INTERVAL '15 minutes'
            WHERE email=:email AND code_hash=:hash AND proof_hash IS NULL AND expires_at>CURRENT_TIMESTAMP
            """, Map.of("proof", proofHash, "email", email, "hash", digest));
    }

    public int consume(String email, String proofHash) {
        return jdbc.update("DELETE FROM signup_email_verifications WHERE email=:email AND proof_hash=:proof AND expires_at>CURRENT_TIMESTAMP",
            Map.of("email", email, "proof", proofHash));
    }

    public void deleteIssued(String email, String digest) {
        jdbc.update("DELETE FROM signup_email_verifications WHERE email=:email AND code_hash=:hash",
                Map.of("email", email, "hash", digest));
    }
}
