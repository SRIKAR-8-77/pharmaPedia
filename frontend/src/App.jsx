import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Toaster } from "react-hot-toast";

import AppLayout from "./components/layout/AppLayout";
import ProjectList from "./pages/ProjectList";
import ProjectCreate from "./pages/ProjectCreate";
import Dashboard from "./pages/Dashboard";
import Signals from "./pages/Signals";
import Canvas from "./pages/Canvas";
import Posts from "./pages/Posts";
import Admin from "./pages/Admin";
import Reports from "./pages/Reports";

const qc = new QueryClient({
  defaultOptions: { queries: { retry: 1, staleTime: 15000 } },
});

export default function App() {
  return (
    <QueryClientProvider client={qc}>
      <BrowserRouter>
        <Routes>
          <Route element={<AppLayout />}>
            <Route index element={<Navigate to="/projects" replace />} />
            <Route path="/projects" element={<ProjectList />} />
            <Route path="/projects/new" element={<ProjectCreate />} />
            <Route path="/projects/:projectId/dashboard" element={<Dashboard />} />
            <Route path="/projects/:projectId/signals" element={<Signals />} />
            <Route path="/projects/:projectId/canvas" element={<Canvas />} />
            <Route path="/projects/:projectId/posts" element={<Posts />} />
            <Route path="/projects/:projectId/reports" element={<Reports />} />
            <Route path="/admin" element={<Admin />} />
          </Route>
        </Routes>
      </BrowserRouter>
      <Toaster
        position="top-right"
        toastOptions={{
          style: {
            background: "var(--color-background-primary)",
            color: "var(--color-text-primary)",
            border: "0.5px solid var(--color-border-secondary)",
            fontSize: 11, borderRadius: 6,
          },
        }}
      />
    </QueryClientProvider>
  );
}
