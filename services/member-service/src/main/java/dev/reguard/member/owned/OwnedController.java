package dev.reguard.member.owned;

import com.fasterxml.jackson.databind.JsonNode;

import org.springframework.http.*;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.*;

import java.net.URI;
import java.util.UUID;

@RestController
@RequestMapping("/api/v1/me/products")
public class OwnedController {
    private final OwnedService service;

    public OwnedController(OwnedService service) {
        this.service = service;
    }

    @PostMapping
    public ResponseEntity<OwnedProduct> create(
            @AuthenticationPrincipal UUID user, @RequestBody JsonNode body) {
        var result = service.create(user, body);

        return ResponseEntity.created(URI.create("/api/v1/me/products/" + result.id()))
                .body(result);
    }

    @GetMapping
    public OwnedService.Page list(
            @AuthenticationPrincipal UUID user,
            @RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "20") int size) {
        return service.list(user, page, size);
    }

    @GetMapping("/{ownedProductId}")
    public OwnedProduct get(@AuthenticationPrincipal UUID user, @PathVariable UUID ownedProductId) {
        return service.get(user, ownedProductId);
    }

    @PatchMapping("/{ownedProductId}")
    public OwnedProduct update(
            @AuthenticationPrincipal UUID user,
            @PathVariable UUID ownedProductId,
            @RequestBody JsonNode body) {
        return service.update(user, ownedProductId, body);
    }

    @DeleteMapping("/{ownedProductId}")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    public void delete(@AuthenticationPrincipal UUID user, @PathVariable UUID ownedProductId) {
        service.delete(user, ownedProductId);
    }

    @GetMapping("/{ownedProductId}/recalls")
    public OwnedService.RecallPage recalls(
            @AuthenticationPrincipal UUID user,
            @PathVariable UUID ownedProductId,
            @RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "20") int size) {
        return service.recalls(user, ownedProductId, page, size);
    }
}
