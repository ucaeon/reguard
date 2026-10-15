import React, { useEffect, useSyncExternalStore } from "react";
import { profileStore } from "../lib/profile-store.js";
export function useProfile() {
  return useSyncExternalStore(profileStore.subscribe, profileStore.getSnapshot);
}
export default function ProfileProvider({ children }) {
  useEffect(() => {
    const refresh = () => {
      if (document.visibilityState === "visible") profileStore.refresh();
    };
    profileStore.refresh();
    window.addEventListener("focus", refresh);
    window.addEventListener("reguard-profile-updated", refresh);
    document.addEventListener("visibilitychange", refresh);
    return () => {
      window.removeEventListener("focus", refresh);
      window.removeEventListener("reguard-profile-updated", refresh);
      document.removeEventListener("visibilitychange", refresh);
    };
  }, []);
  return children;
}
