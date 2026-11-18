import { createRoot } from "react-dom/client";

import App from "./App";
import { PublicPaperView } from "./components/PublicPaperView";
import "./index.css";

const root = document.getElementById("root");
if (!root) {
  throw new Error("root element not found");
}

// /public is the read-only page meant to be shared; everything else is the operator terminal.
const isPublic = window.location.pathname.replace(/\/+$/, "") === "/public";
createRoot(root).render(isPublic ? <PublicPaperView /> : <App />);
