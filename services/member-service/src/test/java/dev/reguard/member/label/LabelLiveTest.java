package dev.reguard.member.label;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.springframework.mock.web.MockMultipartFile;
import javax.imageio.ImageIO;
import java.awt.*;
import java.awt.image.BufferedImage;
import java.io.ByteArrayOutputStream;
import static org.junit.jupiter.api.Assertions.*;

@EnabledIfEnvironmentVariable(named = "VERIFY_LIVE_GEMINI", matches = "true")
class LabelLiveTest {
    @Test
    void extractsSyntheticLabelWithoutRegisteringAnything() throws Exception {
        var image = new BufferedImage(1200, 600, BufferedImage.TYPE_INT_RGB);
        var graphics = image.createGraphics();
        graphics.setColor(Color.WHITE);
        graphics.fillRect(0, 0, 1200, 600);
        graphics.setColor(Color.BLACK);
        graphics.setFont(new Font("SansSerif", Font.BOLD, 38));
        graphics.drawString("TEST LABEL - NOT A REAL PRODUCT", 40, 80);
        graphics.drawString("Product name: Strawberry Jelly", 40, 180);
        graphics.drawString("Manufacturer: ReGuard Test Foods", 40, 270);
        graphics.drawString("Food product report number: 00123456789", 40, 360);
        graphics.dispose();
        var bytes = new ByteArrayOutputStream();
        ImageIO.write(image, "png", bytes);
        var service = new LabelService(System.getenv("GEMINI_API_KEY"),
                System.getenv().getOrDefault("GEMINI_MODEL", "gemini-2.5-flash"), new ObjectMapper());
        var result = service.extract(new MockMultipartFile("image", "label.png", "image/png", bytes.toByteArray()));
        assertTrue(result.requiresConfirmation());
        assertEquals("00123456789", result.fields().get("identifierValue"));
        assertEquals("FOOD_REPORT_NO", result.fields().get("identifierType"));
        assertNotNull(result.fields().get("productName"));
    }
}
