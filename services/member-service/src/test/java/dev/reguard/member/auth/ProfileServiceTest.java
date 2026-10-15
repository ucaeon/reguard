package dev.reguard.member.auth;

import org.junit.jupiter.api.Test;
import org.springframework.security.crypto.password.PasswordEncoder;
import dev.reguard.member.api.ApiException;
import java.util.UUID;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

class ProfileServiceTest {
    private final ProfileRepository repository = mock(ProfileRepository.class);
    private final PasswordEncoder encoder = mock(PasswordEncoder.class);
    private final ProfileService service = new ProfileService(repository, encoder);
    private final UUID user = UUID.randomUUID();
    @Test void invalidNicknameNeverWrites() {
        assertThrows(ApiException.class, () -> service.update(user, new ProfileData.Update("bad\0name", null)));
        verifyNoInteractions(repository);
    }
    @Test void incorrectPasswordDoesNotChangeCredentials() {
        when(repository.lockPassword(user)).thenReturn("stored");
        when(encoder.matches("wrong", "stored")).thenReturn(false);
        assertThrows(ApiException.class, () -> service.password(user, new ProfileData.PasswordChange("wrong", "NewPassword1!")));
        verify(repository, never()).changePassword(any(), any());
    }
    @Test void oversizedCurrentPasswordRejectedBeforeHashCheck() {
        assertThrows(ApiException.class, () -> service.password(user, new ProfileData.PasswordChange("a".repeat(73), "NewPassword1!")));
        verifyNoInteractions(repository, encoder);
    }
    @Test void validPasswordChangeUsesLockedAccount() {
        when(repository.lockPassword(user)).thenReturn("stored");
        when(encoder.matches("old", "stored")).thenReturn(true);
        when(encoder.encode("NewPassword1!")).thenReturn("new-hash");
        service.password(user, new ProfileData.PasswordChange("old", "NewPassword1!"));
        verify(repository).changePassword(user, "new-hash");
    }
}
