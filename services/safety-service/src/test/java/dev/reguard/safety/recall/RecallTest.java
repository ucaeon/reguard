package dev.reguard.safety.recall;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

import dev.reguard.safety.product.*;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.dao.DataAccessResourceFailureException;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

import java.util.*;

class RecallTest {
    RecallRepository repository;
    ProductDetailService products;
    RecallService service;
    MockMvc mvc;

    @BeforeEach
    void setup() {
        repository = mock(RecallRepository.class);
        products = mock(ProductDetailService.class);
        service = new RecallService(repository, products);
        mvc =
                MockMvcBuilders.standaloneSetup(new RecallController(service))
                        .setControllerAdvice(new ProductApiErrors())
                        .build();
    }

    @Test
    void paginationAndTrim() {
        var recall =
                new Recall(
                        UUID.randomUUID(),
                        "FOOD_I0490", "제품",
                        "회사", null,
                        null,
                        null,
                        null,
                        null,
                        null);
        when(repository.list("제품", null, "latest", null, null, 0, 2)).thenReturn(List.of(recall, recall));
        var page = service.list(" 제품 ", 0, 1);
        assertEquals(1, page.items().size());
        assertTrue(page.hasNext());
        service.list(null, Integer.MAX_VALUE, 100);
        verify(repository).list(null, null, "latest", null, null, 214748364700L, 101);
    }

    @Test
    void emptyListAndNoMatchesAreSuccessful() throws Exception {
        mvc.perform(get("/api/v1/recalls"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.items").isEmpty());
        mvc.perform(get("/api/v1/products/{id}/recalls", UUID.randomUUID()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.hasNext").value(false));
    }

    @Test
    void missingResourcesAre404() throws Exception {
        mvc.perform(get("/api/v1/recalls/{id}", UUID.randomUUID()))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.code").value("RECALL_NOT_FOUND"));
        when(products.get(any())).thenThrow(new ProductDetailService.ProductNotFound());
        mvc.perform(get("/api/v1/products/{id}/recalls", UUID.randomUUID()))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.code").value("PRODUCT_NOT_FOUND"));
        verify(repository, never()).forProduct(any(), anyLong(), anyInt());
    }

    @Test
    void invalidRequestsNeverReachDatabase() throws Exception {
        for (String url :
                List.of(
                        "/api/v1/recalls?sort=invalid", "/api/v1/recalls?from=2026-10-12&to=2026-10-01", "/api/v1/recalls?source=invalid", "/api/v1/recalls?page=-1", "/api/v1/recalls?size=101",
                        "/api/v1/recalls?size=0", "/api/v1/recalls?q=",
                        "/api/v1/recalls?size=abc", "/api/v1/recalls/bad-id",
                        "/api/v1/products/bad-id/recalls"))
            mvc.perform(get(url)).andExpect(status().isBadRequest());
        verifyNoInteractions(repository, products);
    }

    @Test
    void sourceFilterCombinesWithSearchAndPagination() throws Exception {
        mvc.perform(get("/api/v1/recalls").param("q", " 제품 ")
                .param("source", "FOOD_I0490").param("page", "1").param("size", "12"))
                .andExpect(status().isOk());
        verify(repository).list("제품", "FOOD_I0490", "latest", null, null, 12L, 13);
    }

    @Test
    void databaseFailureReturns503() throws Exception {
        when(repository.list(any(), any(), any(), any(), any(), anyLong(), anyInt()))
                .thenThrow(new DataAccessResourceFailureException("private SQL"));
        mvc.perform(get("/api/v1/recalls"))
                .andExpect(status().isServiceUnavailable())
                .andExpect(jsonPath("$.code").value("DEPENDENCY_UNAVAILABLE"));
    }
}
