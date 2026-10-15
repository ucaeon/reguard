package dev.reguard.safety.recall;

import dev.reguard.safety.product.ProductSearchService.InvalidSearch;
import java.util.Set;

public record ManualRecallQuery(
        String productName,
        String companyName,
        String modelName,
        String identifierType,
        String identifierValue
) {
    public ManualRecallQuery {
        productName = clean(productName, 500, "productName");
        companyName = clean(companyName, 500, "companyName");
        modelName = clean(modelName, 500, "modelName");
        identifierType = clean(identifierType, 40, "identifierType");
        identifierValue = clean(identifierValue, 255, "identifierValue");
        if (productName == null) throw new InvalidSearch("productName", "제품명을 입력해주세요.");
        if ((identifierType == null) != (identifierValue == null))
            throw new InvalidSearch("identifierType", "식별번호 종류와 값을 함께 입력해주세요.");
        if (identifierType != null && !Set.of("FOOD_REPORT_NO", "KC_CERT_NO", "BARCODE").contains(identifierType))
            throw new InvalidSearch("identifierType", "지원하지 않는 식별번호 종류입니다.");
        if ("FOOD_REPORT_NO".equals(identifierType) && !identifierValue.matches("[0-9]+"))
            throw new InvalidSearch("identifierValue", "품목보고번호는 숫자로 입력해주세요.");
        if ("KC_CERT_NO".equals(identifierType) && !identifierValue.matches("[A-Za-z0-9]+(?:-[A-Za-z0-9]+)+"))
            throw new InvalidSearch("identifierValue", "KC 인증번호 형식을 확인해주세요.");
    }

    private static String clean(String value, int limit, String field) {
        if (value == null || value.isBlank()) return null;
        value = value.strip();
        if (value.length() > limit || value.indexOf(0) >= 0)
            throw new InvalidSearch(field, "입력 길이 또는 형식을 확인해주세요.");
        if (Set.of("-", "해당없음", "데이터없음").contains(value)) return null;
        return value;
    }
}
