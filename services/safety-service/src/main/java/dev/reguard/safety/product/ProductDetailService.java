package dev.reguard.safety.product;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.UUID;

@Service
public class ProductDetailService {
    private final ProductRepository repository;

    public ProductDetailService(ProductRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    public Product get(UUID productId) {
        return repository.findById(productId).orElseThrow(ProductNotFound::new);
    }

    public static class ProductNotFound extends RuntimeException {
        public ProductNotFound() {
            super("제품을 찾을 수 없습니다.");
        }
    }
}
