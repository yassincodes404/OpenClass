import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { Portal } from "./portal";
import { AuthProvider } from "./auth";
import "./styles.css";

createRoot(document.getElementById("root")!).render(
  <QueryClientProvider client={new QueryClient()}><AuthProvider><BrowserRouter><Portal /></BrowserRouter></AuthProvider></QueryClientProvider>,
);
