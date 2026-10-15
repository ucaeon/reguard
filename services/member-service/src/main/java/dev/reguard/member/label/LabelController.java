package dev.reguard.member.label;

import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartFile;

@RestController
@RequestMapping("/api/v1/me/products")
public class LabelController {
    private final LabelService service;

    public LabelController(LabelService service) {
        this.service = service;
    }

    @PostMapping(value = "/extract-label", consumes = "multipart/form-data")
    public LabelService.Draft extract(@RequestPart("image") MultipartFile image) {
        return service.extract(image);
    }
}
