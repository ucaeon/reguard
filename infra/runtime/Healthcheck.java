import java.net.HttpURLConnection;
import java.net.URI;

public class Healthcheck {
    public static void main(String[] args) throws Exception {
        var url = URI.create("http://127.0.0.1:" + System.getenv("SERVER_PORT") + "/actuator/health/readiness");
        var connection = (HttpURLConnection) url.toURL().openConnection();
        connection.setConnectTimeout(1500);
        connection.setReadTimeout(1500);
        try { System.exit(connection.getResponseCode() == 200 ? 0 : 1); }
        finally { connection.disconnect(); }
    }
}
