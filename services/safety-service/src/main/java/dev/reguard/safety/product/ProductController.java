package dev.reguard.safety.product;

import org.springframework.web.bind.annotation.*;

import java.util.UUID;

@RestController
@RequestMapping("/api/v1/products")
public class ProductController {
    private final ProductSearchService service;

    private final ProductDetailService detailService;

    public ProductController(ProductSearchService service, ProductDetailService detailService) {
        this.service = service;
        this.detailService = detailService;
    }

    @GetMapping("/{productId}")
    public Product detail(@PathVariable UUID productId) {
        return detailService.get(productId);
    }

    @GetMapping
    public ProductPage search(
            @RequestParam String q,
            @RequestParam(required = false) String category,
            @RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "20") int size) {
        return service.search(q, category, page, size);
    }
}
