package dev.reguard.member.owned;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

import com.fasterxml.jackson.databind.ObjectMapper;

import dev.reguard.member.api.ApiException;

import org.junit.jupiter.api.*;

import java.time.*;
import java.util.*;

class OwnedServiceTest {
    OwnedRepository repository;
    SafetyClient safety;
    OwnedService service;
    dev.reguard.member.alerts.RecallAlertScanner alerts;
    ObjectMapper mapper = new ObjectMapper();
    UUID user = UUID.randomUUID();
    UUID id = UUID.randomUUID();

    @BeforeEach
    void setup() {
        repository = mock(OwnedRepository.class);
        safety = mock(SafetyClient.class);
        alerts = mock(dev.reguard.member.alerts.RecallAlertScanner.class);
        service = new OwnedService(repository, safety, alerts);
    }

    OwnedProduct product(String type) {
        return new OwnedProduct(
                id,
                type.equals("CATALOG") ? UUID.randomUUID() : null,
                type,
                "제품", "업체",
                null,
                "BARCODE", "123",
                LocalDate.of(2027, 1, 1),
                "lot", OffsetDateTime.now());
    }

    @Test
    void manualRegistrationDoesNotCallSafety() throws Exception {
        when(repository.insert(eq(user), any())).thenAnswer(i -> i.getArgument(1));
        var result =
                service.create(
                        user,
                        mapper.readTree(
                                "{\"registrationType\":\"MANUAL\",\"productName\":\" 제품 \"}"));
        assertEquals("제품", result.productName());
        assertNull(result.catalogProductId());
        verify(alerts).scanProduct(user, result);
        verifyNoInteractions(safety);
    }

    @Test
    void catalogCopiesTrustedIdentifierForCategoryAndDisplay() throws Exception {
        when(repository.insert(eq(user), any())).thenAnswer(i -> i.getArgument(1));
        when(safety.product(id)).thenReturn(mapper.readTree("""
                {"name":"완구","modelName":"콩콩이 우유병","identifiers":[{"type":"KC_CERT_NO","value":"CB063K001-8004A"}]}
                """));
        var body = mapper.createObjectNode().put("registrationType", "CATALOG").put("catalogProductId", id.toString());
        var saved = service.create(user, body);
        assertEquals("KC_CERT_NO", saved.identifierType());
        assertEquals("CB063K001-8004A", saved.identifierValue());
        assertEquals(id, saved.catalogProductId());
    }

    @Test
    void catalogCannotSpoofProductName() throws Exception {
        var body = mapper.readTree("{\"registrationType\":\"CATALOG\",\"productName\":\"조작\"}");
        assertThrows(ApiException.class, () -> service.create(user, body));
        verifyNoInteractions(safety, repository);
    }

    @Test
    void rejectsHalfIdentifierAndUnexpectedFields() throws Exception {
        for (String json :
                List.of(
                        "{\"registrationType\":\"MANUAL\",\"productName\":\"제품\",\"identifierType\":\"BARCODE\"}",
                        "{\"registrationType\":\"MANUAL\",\"productName\":\"제품\",\"userId\":\"other\"}",
                        "{\"registrationType\":\"MANUAL\",\"productName\":12}",
                        "{\"registrationType\":\"MANUAL\",\"productName\":\"제품\",\"expiryDate\":\"2027-02-30\"}")) {
            var body = mapper.readTree(json);
            assertThrows(ApiException.class, () -> service.create(user, body));
        }
        verifyNoInteractions(repository);
    }

    @Test
    void patchNullClearsOnlySpecifiedField() throws Exception {
        var original = product("MANUAL");
        when(repository.lock(user, id)).thenReturn(Optional.of(original));
        when(repository.update(eq(user), any())).thenAnswer(i -> Optional.of(i.getArgument(1)));
        var result = service.update(user, id, mapper.readTree("{\"lotNumber\":null}"));
        assertNull(result.lotNumber());
        assertEquals(original.expiryDate(), result.expiryDate());
        assertEquals(original.productName(), result.productName());
    }

    @Test
    void catalogIdentityIsImmutable() throws Exception {
        when(repository.lock(user, id)).thenReturn(Optional.of(product("CATALOG")));
        var body = mapper.readTree("{\"productName\":\"바꿈\"}");
        assertThrows(ApiException.class, () -> service.update(user, id, body));
        verify(repository, never()).update(any(), any());
    }

    @Test
    void manualRecallUsesSafetyMatching() throws Exception {
        when(repository.find(user, id)).thenReturn(Optional.of(product("MANUAL")));
        when(safety.recalls(any(OwnedProduct.class), eq(0), eq(20))).thenReturn(mapper.readTree("{\"items\":[],\"hasNext\":false}"));
        assertEquals("LOOKUP_COMPLETE", service.recalls(user, id, 0, 20).lookupStatus());
        verify(safety).recalls(any(OwnedProduct.class), eq(0), eq(20));
    }

    @Test
    void nonOwnerNeverCallsSafety() {
        var e = assertThrows(ApiException.class, () -> service.recalls(user, id, 0, 20));
        assertEquals(404, e.status);
        verifyNoInteractions(safety);
    }

    @Test
    void paginationUsesLongAndExtraRow() {
        service.list(user, Integer.MAX_VALUE, 100);
        verify(repository).list(user, 214748364700L, 101);
        assertThrows(ApiException.class, () -> service.list(user, -1, 20));
    }
}
