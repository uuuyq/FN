import { createRoot } from "react-dom/client";
import { ConfigProvider } from "antd";
import { App } from "./App";
import "./style.css";

createRoot(document.getElementById("root")!).render(
  <ConfigProvider theme={{ token: { colorPrimary: "#202123", borderRadius: 12 } }}>
    <App />
  </ConfigProvider>,
);
