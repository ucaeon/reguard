import { defineConfig, loadEnv } from "vite";

export default defineConfig(({ mode }) => {
  const env = { ...loadEnv(mode, "..", ""), ...process.env };
  const member = env.MEMBER_SERVICE_URL || "http://127.0.0.1:8081";
  const safety = env.SAFETY_SERVICE_URL || "http://127.0.0.1:8082";
  const notification = env.NOTIFICATION_SERVICE_URL || "http://127.0.0.1:8083";
  return {
    server: {
      proxy: {
        "/api/v1/me/notifications": {
          target: notification,
          changeOrigin: true,
        },
        "/api/v1/auth": { target: member, changeOrigin: true },
        "/api/v1/me": { target: member, changeOrigin: true },
        "/api": { target: safety, changeOrigin: true },
      },
    },
  };
});
