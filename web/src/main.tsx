import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import { HumanApp } from "./HumanApp";
import "./index.css";

const params = new URLSearchParams(window.location.search);
const humanCode = params.get("human");

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    {humanCode ? <HumanApp code={humanCode} /> : <App />}
  </React.StrictMode>,
);
