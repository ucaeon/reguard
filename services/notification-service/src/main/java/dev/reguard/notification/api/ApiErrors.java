package dev.reguard.notification.api;

import org.springframework.dao.DataAccessException;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.method.annotation.MethodArgumentTypeMismatchException;

import java.util.List;

@RestControllerAdvice
public class ApiErrors {
    public record FieldError(
            String field,
            String message
    ) {}

    public record ErrorBody(
            String code,
            String message,
            List<FieldError> fieldErrors
    ) {}

    @ExceptionHandler(ApiException.class)
    public ResponseEntity<ErrorBody> application(ApiException e) {
        return ResponseEntity.status(e.status)
                .body(new ErrorBody(e.code, e.getMessage(), List.of()));
    }

    @ExceptionHandler({
        HttpMessageNotReadableException.class,
        MethodArgumentTypeMismatchException.class
    })
    public ResponseEntity<ErrorBody> malformed(Exception e) {
        return application(ApiException.invalid("입력 형식이 올바르지 않습니다."));
    }

    @ExceptionHandler(DataAccessException.class)
    public ResponseEntity<ErrorBody> database(DataAccessException e) {
        return application(
                new ApiException(503, "DEPENDENCY_UNAVAILABLE", "정보를 일시적으로 처리할 수 없습니다."));
    }
}
