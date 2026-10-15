import React from "react";
import { createRoot } from "react-dom/client";
import ProfileProvider from "./auth/ProfileProvider.jsx";
import App from "./App.jsx";

createRoot(document.getElementById("root")).render(
  <ProfileProvider>
    <App />
  </ProfileProvider>,
);
