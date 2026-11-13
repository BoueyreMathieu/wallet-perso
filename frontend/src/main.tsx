import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import "./index.css";
import { loadNativeSession } from "./native";
import { applyTheme, watchSystemTheme } from "./theme";

applyTheme();
watchSystemTheme();

function render() {
  ReactDOM.createRoot(document.getElementById("root")!).render(
    <React.StrictMode>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </React.StrictMode>,
  );
}

// Retour de banque arrivé sur une page de l'interface (adresse de retour enregistrée sans
// /api/connections/callback) : on le transmet à l'API au lieu de l'ignorer.
const params = new URLSearchParams(window.location.search);
const bankReturn = params.has("state") && (params.has("code") || params.has("error"));
if (bankReturn) window.location.replace(`/api/connections/callback${window.location.search}`);
else loadNativeSession().finally(render); // appli Android : adresse du serveur et jeton d'abord
