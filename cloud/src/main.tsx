import React from "react";
import ReactDOM from "react-dom/client";
import { ConvexReactClient } from "convex/react";
import { ConvexBetterAuthProvider, type AuthClient } from "@convex-dev/better-auth/react";
import { authClient } from "./lib/authClient";
import App from "./App";
import "./styles.css";

const convexUrl = import.meta.env.VITE_CONVEX_URL;
if (!convexUrl) {
  throw new Error("VITE_CONVEX_URL is missing. Follow cloud/README.md to connect a Convex deployment.");
}

const convex = new ConvexReactClient(convexUrl, { expectAuth: true });

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
      <ConvexBetterAuthProvider client={convex} authClient={authClient as unknown as AuthClient}>
      <App />
    </ConvexBetterAuthProvider>
  </React.StrictMode>,
);
