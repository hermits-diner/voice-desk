import React from "react";
import ReactDOM from "react-dom/client";

import App from "./App";
import "./styles.css";

// 브라우저 기본 컨텍스트 메뉴와 F5 새로고침은 데스크톱 앱에서 어색하다.
document.addEventListener("contextmenu", (e) => {
  const el = e.target as HTMLElement;
  if (!el.closest("input, textarea, [data-selectable]")) e.preventDefault();
});

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
