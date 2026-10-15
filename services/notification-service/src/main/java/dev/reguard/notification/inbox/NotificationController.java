package dev.reguard.notification.inbox;


import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.*;

import java.util.*;
import dev.reguard.notification.inbox.NotificationData.*;

@RestController
@RequestMapping("/api/v1/me/notifications")
public class NotificationController {
    private final NotificationService service;
    public NotificationController(NotificationService service) { this.service = service; }
    @GetMapping
    public Page list(@AuthenticationPrincipal UUID user, @RequestParam(defaultValue="0") int page, @RequestParam(defaultValue="20") int size) { return service.list(user, page, size); }
    @GetMapping("/unread-count")
    public UnreadCount unread(@AuthenticationPrincipal UUID user) { return service.unread(user); }
    @PatchMapping("/{notificationId}/read")
    public Notification read(@AuthenticationPrincipal UUID user, @PathVariable UUID notificationId) { return service.read(user, notificationId); }
}
