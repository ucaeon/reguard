import React, { useSyncExternalStore } from "react";
import CatalogPage from "./CatalogPage.jsx";
import ManualRegistration from "./items/ManualRegistration.jsx";
import NotificationsPage from "./notifications/NotificationsPage.jsx";
import MyItemsPage from "./items/MyItemsPage.jsx";
import RecallDetailPage from "./recalls/RecallDetailPage.jsx";
import LandingPage from "./landing/LandingPage.jsx";
import AuthPage from "./auth/AuthPage.jsx";
import ResetPasswordPage from "./auth/ResetPasswordPage.jsx";
import SettingsPage from "./settings/SettingsPage.jsx";
import AboutPage from "./about/AboutPage.jsx";

const subscribe = (callback) => {
  window.addEventListener("popstate", callback);
  return () => window.removeEventListener("popstate", callback);
};
export default function App() {
  const url = useSyncExternalStore(subscribe, () => location.href);
  const initial = new URLSearchParams(new URL(url).search);
  const view = initial.get("view") || (initial.has("q") ? "search" : "home");
  if (
    location.pathname === "/reset-password" ||
    initial.get("view") === "reset-password"
  )
    return <ResetPasswordPage />;
  if (view === "login" || view === "signup")
    return <AuthPage signup={view === "signup"} />;
  if (view === "home") return <LandingPage />;
  if (view === "register") return <ManualRegistration />;
  if (view === "notifications") return <NotificationsPage />;
  if (view === "items") return <MyItemsPage />;
  if (view === "settings") return <SettingsPage />;
  if (view === "about") return <AboutPage />;
  if (view === "recall")
    return <RecallDetailPage id={initial.get("id") || ""} />;

  if (!["search", "recalls"].includes(view)) return <LandingPage />;
  return (
    <CatalogPage key={url} view={view === "recalls" ? "recalls" : "search"} />
  );
}
