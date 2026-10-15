package dev.reguard.member.auth;

import dev.reguard.member.api.ApiException;
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.util.Base64;
import javax.imageio.ImageIO;
import javax.imageio.stream.MemoryCacheImageInputStream;

final class ProfilePhoto {
    private static final int MAX_BYTES = 1024 * 1024;
    private static final int MAX_DIMENSION = 2048;
    private static final int MAX_DATA_URL_LENGTH = 1_500_000;
    private ProfilePhoto() {}

    static byte[] normalize(String value) {
        if (value == null || value.isBlank()) return null;
        if (value.length() > MAX_DATA_URL_LENGTH
                || !value.matches("^data:image/(png|jpeg);base64,[A-Za-z0-9+/=]+$"))
            throw invalid();
        try {
            byte[] bytes = Base64.getDecoder().decode(value.substring(value.indexOf(',') + 1));
            if (bytes.length > MAX_BYTES) throw new IllegalArgumentException();
            // Decode in memory so uploaded photos never create a local ImageIO cache file.
            try (var input = new MemoryCacheImageInputStream(new ByteArrayInputStream(bytes))) {
                var readers = ImageIO.getImageReaders(input);
                if (!readers.hasNext()) throw new IllegalArgumentException();
                var reader = readers.next();
                try {
                    reader.setInput(input);
                    int width = reader.getWidth(0), height = reader.getHeight(0);
                    if (width < 1 || height < 1 || width > MAX_DIMENSION || height > MAX_DIMENSION)
                        throw new IllegalArgumentException();
                    var image = reader.read(0);
                    var output = new ByteArrayOutputStream();
                    ImageIO.write(image, "png", output);
                    if (output.size() > MAX_BYTES) throw new IllegalArgumentException();
                    return output.toByteArray();
                } finally {
                    reader.dispose();
                }
            }
        } catch (IOException | RuntimeException failure) {
            throw invalid();
        }
    }
    private static ApiException invalid() {
        return ApiException.invalid("사진은 1MB 이하, 가로·세로 2048px 이하의 JPG 또는 PNG로 선택해 주세요.");
    }
}
