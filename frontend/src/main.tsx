import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import EvalLab from "./EvalLab";
import "./styles.css";

const RootView = window.location.pathname === "/eval" ? EvalLab : App;

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <RootView />
  </StrictMode>,
);
