import React from "react";
import { Link, Route, Routes } from "react-router-dom";
import { ProjectsPage } from "./pages/ProjectsPage";
import { ProjectDetailPage } from "./pages/ProjectDetailPage";
import { ExecutionPage } from "./pages/ExecutionPage";
import { ReportPage } from "./pages/ReportPage";

export function App() {
  return (
    <div style={{ padding: 16, fontFamily: "Segoe UI, sans-serif" }}>
      <h1>AI Test Agent</h1>
      <nav style={{ display: "flex", gap: 12 }}>
        <Link to="/projects">Projects</Link>
      </nav>
      <Routes>
        <Route path="/projects" element={<ProjectsPage />} />
        <Route path="/projects/:id" element={<ProjectDetailPage />} />
        <Route path="/execute/:execId" element={<ExecutionPage />} />
        <Route path="/reports/:reportId" element={<ReportPage />} />
      </Routes>
    </div>
  );
}
