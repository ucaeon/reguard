package dev.reguard.safety.recall;

import org.springframework.web.bind.annotation.*;

import java.util.UUID;

@RestController
@RequestMapping("/api/v1")
public class RecallController {
    private final RecallService service;

    public RecallController(RecallService service) {
        this.service = service;
    }

    @GetMapping("/recalls")
    public RecallPage<Recall> list(
            @RequestParam(required = false) String q,
            @RequestParam(required = false) String source,
            @RequestParam(defaultValue = "latest") String sort,
            @RequestParam(required = false) java.time.LocalDate from,
            @RequestParam(required = false) java.time.LocalDate to,
            @RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "20") int size) {
        return service.list(q, source, sort, from, to, page, size);
    }

    @PostMapping("/recalls/match")
    public RecallPage<ProductRecall> forManual(
            @RequestBody ManualRecallQuery query,
            @RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "20") int size) {
        return service.forManual(query, page, size);
    }

    @GetMapping("/recalls/{recallId}")
    public Recall detail(@PathVariable UUID recallId) {
        return service.detail(recallId);
    }

    @GetMapping("/products/{productId}/recalls")
    public RecallPage<ProductRecall> forProduct(
            @PathVariable UUID productId,
            @RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "20") int size) {
        return service.forProduct(productId, page, size);
    }
}
