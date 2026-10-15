package dev.reguard.safety.recall;

import dev.reguard.safety.product.ProductDetailService;
import dev.reguard.safety.product.ProductSearchService.InvalidSearch;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;
import java.util.UUID;

@Service
@Transactional(readOnly = true)
public class RecallService {
    private final RecallRepository repository;
    private final ProductDetailService products;

    public RecallService(RecallRepository repository, ProductDetailService products) {
        this.repository = repository;
        this.products = products;
    }

    public RecallPage<Recall> list(String q, int page, int size) {
        return list(q, null, page, size);
    }

    public RecallPage<Recall> list(String q, String source, int page, int size) {
        return list(q, source, "latest", null, null, page, size);
    }

    public RecallPage<Recall> list(String q, String source, String sort, java.time.LocalDate from, java.time.LocalDate to, int page, int size) {
        if (!List.of("latest", "oldest").contains(sort)) throw new InvalidSearch("sort", "정렬 기준을 확인해주세요.");
        if (from != null && to != null && from.isAfter(to)) throw new InvalidSearch("from", "기간을 확인해주세요.");
        validate(page, size);
        if (source != null && !List.of("FOOD_I0490", "SAFETY_RECALL").contains(source))
            throw new InvalidSearch("source", "올바른 분류를 선택해주세요.");

        if (q != null && (q.strip().isEmpty() || q.strip().length() > 100))
            throw new InvalidSearch("q", "검색어를 1~100자로 입력해주세요.");

        return page(
                repository.list(q == null ? null : q.strip(), source, sort, from, to, (long) page * size, size + 1),
                page,
                size);
    }

    public Recall detail(UUID id) {
        return repository.find(id).orElseThrow(RecallNotFound::new);
    }

    public RecallPage<ProductRecall> forProduct(UUID id, int page, int size) {
        validate(page, size);
        products.get(id);

        return page(repository.forProduct(id, (long) page * size, size + 1), page, size);
    }

    public RecallPage<ProductRecall> forManual(ManualRecallQuery query, int page, int size) {
        validate(page, size);
        return page(repository.forManual(query, (long) page * size, size + 1), page, size);
    }

    private void validate(int page, int size) {
        if (page < 0) {
            throw new InvalidSearch("page", "page는 0 이상이어야 합니다.");
        }
        if (size < 1 || size > 100) {
            throw new InvalidSearch("size", "size는 1~100이어야 합니다.");
        }
    }

    private <T> RecallPage<T> page(List<T> rows, int page, int size) {
        return new RecallPage<>(
                List.copyOf(rows.subList(0, Math.min(rows.size(), size))),
                page,
                size,
                rows.size() > size);
    }

    public static class RecallNotFound extends RuntimeException {
        public RecallNotFound() {
            super("리콜 정보를 찾을 수 없습니다.");
        }
    }
}
