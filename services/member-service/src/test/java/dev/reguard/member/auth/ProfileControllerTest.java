package dev.reguard.member.auth;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;
import java.awt.image.BufferedImage;
import java.io.ByteArrayOutputStream;
import java.util.Base64;
import javax.imageio.ImageIO;
class ProfileControllerTest {
 @Test void acceptsRealImageAndNormalizes() throws Exception {var out=new ByteArrayOutputStream();ImageIO.write(new BufferedImage(4,4,BufferedImage.TYPE_INT_RGB),"png",out);var image=ProfilePhoto.normalize("data:image/png;base64,"+Base64.getEncoder().encodeToString(out.toByteArray()));assertNotNull(ImageIO.read(new java.io.ByteArrayInputStream(image)));}
 @Test void rejectsFakeImageAndLargePayload(){assertThrows(RuntimeException.class,()->ProfilePhoto.normalize("data:image/png;base64,aGVsbG8="));assertThrows(RuntimeException.class,()->ProfilePhoto.normalize("x".repeat(1500001)));assertNull(ProfilePhoto.normalize(null));}
}
