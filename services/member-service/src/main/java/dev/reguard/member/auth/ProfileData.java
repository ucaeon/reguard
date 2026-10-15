package dev.reguard.member.auth;

public final class ProfileData {
    private ProfileData() {}
    public record Profile(String email, String displayName, String photo) {}
    public record Update(String displayName, String photo) {}
    public record PasswordChange(String currentPassword, String newPassword) {}
}
