package dev.reguard.member.label;

import com.fasterxml.jackson.databind.ObjectMapper;
import dev.reguard.member.api.ApiException;
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockMultipartFile;
import java.awt.image.BufferedImage;
import java.io.ByteArrayOutputStream;
import javax.imageio.ImageIO;
import static org.junit.jupiter.api.Assertions.*;

class LabelServiceTest {
    private final ObjectMapper mapper = new ObjectMapper();

    @Test
    void clearsHallucinatedIdentifierButKeepsDraft() throws Exception {
        var draft = LabelService.validate(mapper.readTree("""
                {"productName":"슬라임", "identifierType":"KC_CERT_NO", "identifierValue":"모름"}
                """));
        assertEquals("슬라임", draft.fields().get("productName"));
        assertNull(draft.fields().get("identifierValue"));
        assertTrue(draft.requiresConfirmation());
    }

    @Test
    void preservesLeadingZeroesAndRejectsNumericJson() throws Exception {
        var draft = LabelService.validate(mapper.readTree("""
                {"productName":"식품", "identifierType":"FOOD_REPORT_NO", "identifierValue":"001234"}
                """));
        assertEquals("001234", draft.fields().get("identifierValue"));
        assertThrows(ApiException.class, () -> LabelService.validate(mapper.readTree("{\"productName\":42}")));
    }

    @Test
    void rejectsFakeImageAndOversize() {
        assertThrows(ApiException.class, () -> LabelService.checkedImage(
                new MockMultipartFile("image", "fake.png", "image/png", "not an image".getBytes())));
        assertThrows(ApiException.class, () -> LabelService.checkedImage(
                new MockMultipartFile("image", new byte[5*1024*1024+1])));
    }

    @Test
    void validatesRealImageAndMissingKey() throws Exception {
        var output = new ByteArrayOutputStream();
        ImageIO.write(new BufferedImage(20, 20, BufferedImage.TYPE_INT_RGB), "png", output);
        var image = new MockMultipartFile("image", "label.png", "image/png", output.toByteArray());
        assertTrue(LabelService.checkedImage(image).length > 0);
        var error = assertThrows(ApiException.class, () -> new LabelService("", "test", mapper).extract(image));
        assertEquals("LABEL_AI_NOT_CONFIGURED", error.code);
    }
}
