package dev.reguard.safety.product;

import static org.hamcrest.Matchers.*;
import static org.mockito.Mockito.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.dao.DataAccessResourceFailureException;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

import java.util.*;

class ProductDetailTest {
    ProductRepository repository;
    MockMvc mvc;

    @BeforeEach
    void setup() {
        repository = mock(ProductRepository.class);
        mvc =
                MockMvcBuilders.standaloneSetup(
                                new ProductController(
                                        new ProductSearchService(repository),
                                        new ProductDetailService(repository)))
                        .setControllerAdvice(new ProductApiErrors())
                        .build();
    }

    @Test
    void returnsProductWithIdentifiersAndNullImage() throws Exception {
        var id = UUID.randomUUID();
        when(repository.findById(id))
                .thenReturn(
                        Optional.of(
                                new Product(
                                        id,
                                        "비타민", "업체",
                                        "HEALTH_SUPPLEMENT", null,
                                        null,
                                        List.of(
                                                new Product.Identifier(
                                                        "FOOD_REPORT_NO", "12345")))));
        mvc.perform(get("/api/v1/products/{id}", id))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(id.toString()))
                .andExpect(jsonPath("$.name").value("비타민"))
                .andExpect(jsonPath("$.imageUrl").value(nullValue()))
                .andExpect(jsonPath("$.identifiers[0].value").value("12345"));
    }

    @Test
    void missingProductReturns404() throws Exception {
        mvc.perform(get("/api/v1/products/{id}", UUID.randomUUID()))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.code").value("PRODUCT_NOT_FOUND"));
    }

    @Test
    void malformedIdNeverQueriesDatabase() throws Exception {
        mvc.perform(get("/api/v1/products/not-a-uuid"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.fieldErrors[0].field").value("productId"));
        verifyNoInteractions(repository);
    }

    @Test
    void databaseFailureDoesNotLeakDetails() throws Exception {
        when(repository.findById(any()))
                .thenThrow(new DataAccessResourceFailureException("secret SQL"));
        mvc.perform(get("/api/v1/products/{id}", UUID.randomUUID()))
                .andExpect(status().isServiceUnavailable())
                .andExpect(jsonPath("$.code").value("DEPENDENCY_UNAVAILABLE"))
                .andExpect(content().string(not(containsString("secret SQL"))));
    }
}
