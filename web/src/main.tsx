import "@fontsource-variable/public-sans";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./shared/theme/tokens.css";
import "./shared/theme/global.css";
import { App } from "./app/App";

createRoot(document.getElementById("root") as HTMLElement).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
