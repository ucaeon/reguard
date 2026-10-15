package dev.reguard.notification.api;

public class ApiException extends RuntimeException {
    public final int status;
    public final String code;

    public ApiException(int status, String code, String message) {
        super(message);
        this.status = status;
        this.code = code;
    }

    public static ApiException invalid(String message) {
        return new ApiException(400, "INVALID_REQUEST", message);
    }
}
