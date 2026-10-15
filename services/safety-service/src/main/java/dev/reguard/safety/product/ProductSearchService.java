package dev.reguard.safety.product;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.Set;

@Service
public class ProductSearchService {
    private final ProductRepository repository;

    public ProductSearchService(ProductRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    public ProductPage search(String q, String category, int page, int size) {
        if (q == null || q.strip().isEmpty() || q.strip().length() > 100)
            throw new InvalidSearch("q", "검색어를 1~100자로 입력해주세요.");

        if (page < 0) {
            throw new InvalidSearch("page", "page는 0 이상이어야 합니다.");
        }
        if (size < 1 || size > 100) {
            throw new InvalidSearch("size", "size는 1~100이어야 합니다.");
        }
        if (category != null && !Set.of("FOOD", "HEALTH_SUPPLEMENT").contains(category))
            throw new InvalidSearch("category", "지원하지 않는 제품 분류입니다.");
        var results = repository.search(q.strip(), category, (long) page * size, size + 1);
        boolean hasNext = results.size() > size;

        return new ProductPage(
                results.subList(0, Math.min(results.size(), size)), page, size, hasNext);
    }

    public static class InvalidSearch extends RuntimeException {
        private final String field;

        public InvalidSearch(String field, String message) {
            super(message);
            this.field = field;
        }

        public String field() {
            return field;
        }
    }
}
