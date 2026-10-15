package dev.reguard.safety.product;

import org.springframework.dao.DataAccessException;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.MissingServletRequestParameterException;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.method.annotation.MethodArgumentTypeMismatchException;

import java.util.List;

@RestControllerAdvice(
        assignableTypes = {
            ProductController.class,
            dev.reguard.safety.recall.RecallController.class
        })
public class ProductApiErrors {
    public record FieldError(
            String field,
            String message
    ) {}

    public record ApiError(
            String code,
            String message,
            List<FieldError> fieldErrors
    ) {}

    @ExceptionHandler(ProductSearchService.InvalidSearch.class)
    public ResponseEntity<ApiError> invalid(ProductSearchService.InvalidSearch e) {
        return badRequest(e.field(), e.getMessage());
    }

    @ExceptionHandler(MissingServletRequestParameterException.class)
    public ResponseEntity<ApiError> missing(MissingServletRequestParameterException e) {
        return badRequest(e.getParameterName(), "필수 검색 조건을 입력해주세요.");
    }

    @ExceptionHandler(MethodArgumentTypeMismatchException.class)
    public ResponseEntity<ApiError> type(MethodArgumentTypeMismatchException e) {
        return badRequest(e.getName(), "입력 형식이 올바르지 않습니다.");
    }

    @ExceptionHandler(ProductDetailService.ProductNotFound.class)
    public ResponseEntity<ApiError> notFound(ProductDetailService.ProductNotFound e) {
        return ResponseEntity.status(404)
                .body(new ApiError("PRODUCT_NOT_FOUND", e.getMessage(), List.of()));
    }

    @ExceptionHandler(dev.reguard.safety.recall.RecallService.RecallNotFound.class)
    public ResponseEntity<ApiError> recallNotFound(RuntimeException e) {
        return ResponseEntity.status(404)
                .body(new ApiError("RECALL_NOT_FOUND", e.getMessage(), List.of()));
    }

    @ExceptionHandler(DataAccessException.class)
    public ResponseEntity<ApiError> database(DataAccessException e) {
        return ResponseEntity.status(503)
                .body(new ApiError("DEPENDENCY_UNAVAILABLE", "정보를 일시적으로 조회할 수 없습니다.", List.of()));
    }

    private ResponseEntity<ApiError> badRequest(String field, String message) {
        return ResponseEntity.badRequest()
                .body(
                        new ApiError(
                                "INVALID_REQUEST", message,
                                List.of(new FieldError(field, message))));
    }
}
