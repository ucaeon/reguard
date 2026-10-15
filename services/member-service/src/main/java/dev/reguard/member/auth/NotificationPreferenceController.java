package dev.reguard.member.auth;

import java.util.UUID;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/v1/me/notification-preferences")
public class NotificationPreferenceController {
 private final NotificationPreferenceService service;
 public NotificationPreferenceController(NotificationPreferenceService service){this.service=service;}
 public record Preference(Boolean enabled){}
 @GetMapping public Preference get(@AuthenticationPrincipal UUID user){return new Preference(service.get(user));}
 @PutMapping public Preference save(@AuthenticationPrincipal UUID user,@RequestBody Preference preference){return new Preference(service.save(user,preference.enabled()));}
}
