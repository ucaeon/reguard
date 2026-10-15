package dev.reguard.safety.product;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

import java.util.*;

class ProductSearchTest {
    ProductRepository repository;
    ProductSearchService service;
    MockMvc mvc;

    @BeforeEach
    void setup() {
        repository = mock(ProductRepository.class);
        service = new ProductSearchService(repository);
        mvc =
                MockMvcBuilders.standaloneSetup(
                                new ProductController(
                                        service, new ProductDetailService(repository)))
                        .setControllerAdvice(new ProductApiErrors())
                        .build();
    }

    @Test
    void paginationKeepsOnlyRequestedItems() {
        var p = new Product(UUID.randomUUID(), "비타민", null, "FOOD", null, null, List.of());
        when(repository.search("비타민", null, 2L, 3)).thenReturn(List.of(p, p, p));
        var result = service.search("  비타민  ", null, 1, 2);
        assertEquals(2, result.items().size());
        assertTrue(result.hasNext());
        assertNull(result.items().getFirst().imageUrl());
    }

    @Test
    void emptySearchReturns200() throws Exception {
        mvc.perform(get("/api/v1/products").param("q", "없는상품"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.items").isEmpty())
                .andExpect(jsonPath("$.hasNext").value(false));
    }

    @Test
    void invalidInputNeverQueriesDatabase() throws Exception {
        for (String query : List.of("", "   ", "a".repeat(101)))
            mvc.perform(get("/api/v1/products").param("q", query))
                    .andExpect(status().isBadRequest());

        for (String[] pair :
                List.of(
                        new String[] {"page", "-1"},
                        new String[] {"size", "0"},
                        new String[] {"size", "101"},
                        new String[] {"page", "abc"},
                        new String[] {"category", "OTHER"}))
            mvc.perform(get("/api/v1/products").param("q", "제품").param(pair[0], pair[1]))
                    .andExpect(status().isBadRequest())
                    .andExpect(jsonPath("$.code").value("INVALID_REQUEST"));
        mvc.perform(get("/api/v1/products")).andExpect(status().isBadRequest());
        verifyNoInteractions(repository);
    }

    @Test
    void offsetDoesNotOverflowInteger() {
        service.search("제품", "FOOD", Integer.MAX_VALUE, 100);
        verify(repository).search("제품", "FOOD", 214748364700L, 101);
    }

    @Test
    void databaseFailureIsNotEmptySuccess() throws Exception {
        when(repository.search(anyString(), isNull(), anyLong(), anyInt()))
                .thenThrow(
                        new org.springframework.dao.DataAccessResourceFailureException(
                                "secret SQL"));
        mvc.perform(get("/api/v1/products").param("q", "제품"))
                .andExpect(status().isServiceUnavailable())
                .andExpect(jsonPath("$.code").value("DEPENDENCY_UNAVAILABLE"))
                .andExpect(
                        content()
                                .string(
                                        org.hamcrest.Matchers.not(
                                                org.hamcrest.Matchers.containsString(
                                                        "secret SQL"))));
    }
}
