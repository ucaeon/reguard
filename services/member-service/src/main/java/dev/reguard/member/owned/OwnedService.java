package dev.reguard.member.owned;

import com.fasterxml.jackson.databind.JsonNode;

import dev.reguard.member.api.ApiException;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.*;
import java.util.*;

@Service
public class OwnedService {
    public record Page(
            List<OwnedProduct> items,
            int page,
            int size,
            boolean hasNext
    ) {}

    public record RecallPage(
            String lookupStatus,
            String message,
            List<JsonNode> items,
            int page,
            int size,
            boolean hasNext
    ) {}

    private static final Set<String> CREATE =
            Set.of(
                    "registrationType", "catalogProductId",
                    "productName", "companyName",
                    "modelName", "identifierType",
                    "identifierValue", "expiryDate",
                    "lotNumber");
    private static final Set<String> MANUAL_EDIT =
            Set.of(
                    "productName", "companyName",
                    "modelName", "identifierType",
                    "identifierValue", "expiryDate",
                    "lotNumber");
    private final OwnedRepository repository;
    private final SafetyClient safety;
    private final dev.reguard.member.alerts.RecallAlertScanner alerts;

    public OwnedService(OwnedRepository repository, SafetyClient safety, dev.reguard.member.alerts.RecallAlertScanner alerts) {
        this.repository = repository;
        this.safety = safety;
        this.alerts = alerts;
    }

    public Page list(UUID user, int page, int size) {
        pagination(page, size);
        var rows = repository.list(user, (long) page * size, size + 1);

        return new Page(
                List.copyOf(rows.subList(0, Math.min(size, rows.size()))),
                page,
                size,
                rows.size() > size);
    }

    public OwnedProduct get(UUID user, UUID id) {
        return repository.find(user, id).orElseThrow(OwnedService::notFound);
    }

    public OwnedProduct create(UUID user, JsonNode body) {
        fields(body, CREATE);
        String type = text(body, "registrationType", 20, true);
        String name, company, model, identifierType, identifierValue;
        UUID catalog = null;

        if ("CATALOG".equals(type)) {
            for (String field :
                    List.of(
                            "productName", "companyName",
                            "modelName", "identifierType",
                            "identifierValue"))
                if (body.has(field)) {
                    throw ApiException.invalid("검색 등록에서는 제품 정보를 직접 입력할 수 없습니다.");
                }
            try {
                catalog = UUID.fromString(text(body, "catalogProductId", 36, true));
            } catch (IllegalArgumentException e) {
                throw ApiException.invalid("catalogProductId는 UUID여야 합니다.");
            }
            JsonNode product = safety.product(catalog);
            name = text(product, "name", 500, true);
            company = text(product, "companyName", 500, false);
            model = text(product, "modelName", 500, false);
            identifierType = null;
            identifierValue = null;
            for (JsonNode identifier : product.path("identifiers")) {
                String candidateType = identifier.path("type").asText();
                String candidateValue = identifier.path("value").asText();
                if (("KC_CERT_NO".equals(candidateType) && candidateValue.matches("[A-Za-z0-9]+(?:-[A-Za-z0-9]+)+"))
                        || ("FOOD_REPORT_NO".equals(candidateType) && candidateValue.matches("[0-9]+"))) {
                    identifierType = candidateType;
                    identifierValue = candidateValue;
                    break;
                }
            }
        } else if ("MANUAL".equals(type)) {
            if (body.hasNonNull("catalogProductId"))
                throw ApiException.invalid("직접 등록에는 catalogProductId를 지정할 수 없습니다.");
            name = text(body, "productName", 500, true);
            company = text(body, "companyName", 500, false);
            model = text(body, "modelName", 500, false);
            identifierType = text(body, "identifierType", 40, false);
            identifierValue = text(body, "identifierValue", 255, false);
        } else throw ApiException.invalid("registrationType은 CATALOG 또는 MANUAL이어야 합니다.");
        pair(identifierType, identifierValue);

        var saved = repository.insert(
                user,
                new OwnedProduct(
                        UUID.randomUUID(),
                        catalog,
                        type,
                        name,
                        company,
                        model,
                        identifierType,
                        identifierValue,
                        date(body, "expiryDate"),
                        text(body, "lotNumber", 255, false),
                        null));
        alerts.scanProduct(user, saved);
        return saved;
    }

    @Transactional
    public OwnedProduct update(UUID user, UUID id, JsonNode body) {
        OwnedProduct old = repository.lock(user, id).orElseThrow(OwnedService::notFound);
        fields(
                body,
                "CATALOG".equals(old.registrationType())
                        ? Set.of("expiryDate", "lotNumber")
                        : MANUAL_EDIT);

        if (body.isEmpty()) {
            throw ApiException.invalid("수정할 값을 입력해주세요.");
        }
        String identifierType = changed(body, "identifierType", old.identifierType(), 40, false);
        String identifierValue =
                changed(body, "identifierValue", old.identifierValue(), 255, false);
        pair(identifierType, identifierValue);
        var updated =
                new OwnedProduct(
                        id,
                        old.catalogProductId(),
                        old.registrationType(),
                        changed(body, "productName", old.productName(), 500, true),
                        changed(body, "companyName", old.companyName(), 500, false),
                        changed(body, "modelName", old.modelName(), 500, false),
                        identifierType,
                        identifierValue,
                        body.has("expiryDate") ? date(body, "expiryDate") : old.expiryDate(),
                        changed(body, "lotNumber", old.lotNumber(), 255, false),
                        old.createdAt());

        return repository.update(user, updated).orElseThrow(OwnedService::notFound);
    }

    public void delete(UUID user, UUID id) {
        if (!repository.delete(user, id)) {
            throw notFound();
        }
    }

    public RecallPage recalls(UUID user, UUID id, int page, int size) {
        pagination(page, size);
        var product = get(user, id);

        if (product.catalogProductId() == null && product.identifierType() == null
                && product.companyName() == null)
            return new RecallPage("INSUFFICIENT_DETAILS", "업체명 또는 식별번호를 추가해주세요.",
                    List.of(), page, size, false);
        var result = safety.recalls(product, page, size);
        List<JsonNode> items = new ArrayList<>();
        result.path("items").forEach(items::add);

        return new RecallPage(
                "LOOKUP_COMPLETE", "조회된 연결 정보이며 제조일·소비기한 등 회수 조건을 확인해야 합니다.",
                List.copyOf(items),
                page,
                size,
                result.path("hasNext").asBoolean());
    }

    private static ApiException notFound() {
        return new ApiException(404, "OWNED_PRODUCT_NOT_FOUND", "내 물건을 찾을 수 없습니다.");
    }

    private void pagination(int page, int size) {
        if (page < 0 || size < 1 || size > 100)
            throw ApiException.invalid("page는 0 이상, size는 1~100이어야 합니다.");
    }

    private void fields(JsonNode body, Set<String> allowed) {
        if (body == null || !body.isObject()) {
            throw ApiException.invalid("JSON 객체를 입력해주세요.");
        }
        body.fieldNames()
                .forEachRemaining(
                        key -> {
                            if (!allowed.contains(key))
                                throw ApiException.invalid("허용되지 않는 필드입니다: " + key);
                        });
    }

    private String changed(JsonNode body, String key, String old, int max, boolean required) {
        return body.has(key) ? text(body, key, max, required) : old;
    }

    private String text(JsonNode body, String key, int max, boolean required) {
        JsonNode node = body.get(key);

        if (node == null || node.isNull()) {
            if (required) {
                throw ApiException.invalid(key + " 값이 필요합니다.");
            }
            return null;
        }
        if (!node.isTextual()) {
            throw ApiException.invalid(key + "는 문자열이어야 합니다.");
        }
        String value = node.asText().strip();

        if (value.length() > max || value.indexOf(0) >= 0 || (required && value.isEmpty()))
            throw ApiException.invalid(key + " 길이 또는 값이 올바르지 않습니다.");

        return value.isEmpty() ? null : value;
    }

    private LocalDate date(JsonNode body, String key) {
        String value = text(body, key, 10, false);

        if (value == null) {
            return null;
        }
        try {
            return LocalDate.parse(value);
        } catch (DateTimeException e) {
            throw ApiException.invalid(key + "는 YYYY-MM-DD 형식이어야 합니다.");
        }
    }

    private void pair(String type, String value) {
        if ((type == null) != (value == null))
            throw ApiException.invalid("식별번호 종류와 값은 함께 입력하거나 함께 비워주세요.");
        if (type != null && !Set.of("FOOD_REPORT_NO", "KC_CERT_NO", "BARCODE").contains(type))
            throw ApiException.invalid("지원 식별번호: FOOD_REPORT_NO, KC_CERT_NO, BARCODE");
        if ("FOOD_REPORT_NO".equals(type) && !value.matches("[0-9]+"))
            throw ApiException.invalid("품목보고번호는 숫자로 입력해주세요.");
        if ("KC_CERT_NO".equals(type) && !value.matches("[A-Za-z0-9]+(?:-[A-Za-z0-9]+)+"))
            throw ApiException.invalid("KC 인증번호 형식을 확인해주세요.");

    }
}
