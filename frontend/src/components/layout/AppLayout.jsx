import { Outlet } from "react-router-dom";
import Sidebar from "./Sidebar";

export default function AppLayout() {
  return (
    <div style={{ display: "flex", height: "100vh", overflow: "hidden" }}>
      <Sidebar />
      <main style={{
        marginLeft: "var(--sidebar-width)",
        flex: 1,
        overflow: "hidden",
        background: "var(--color-background-primary)",
        display: "flex",
        flexDirection: "column",
      }}>
        <Outlet />
      </main>
    </div>
  );
}
