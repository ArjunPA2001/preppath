import { Routes, Route, Navigate } from "react-router-dom";
import ProtectedRoute from "./components/ProtectedRoute.jsx";
import Login from "./pages/Login.jsx";

import ExecDashboard from "./pages/executive/Dashboard.jsx";

import FeederPaths from "./pages/feeder/Paths.jsx";
import FeederPathEditor from "./pages/feeder/PathEditor.jsx";
import FeederCandidates from "./pages/feeder/Candidates.jsx";

import CandidateHome from "./pages/candidate/Home.jsx";
import CandidateTest from "./pages/candidate/Test.jsx";
import CandidateChat from "./pages/candidate/Chat.jsx";
import CandidateProgress from "./pages/candidate/Progress.jsx";

import { getUser } from "./auth.js";

function HomeRedirect() {
  const u = getUser();
  if (!u) return <Navigate to="/login" replace />;
  if (u.role === "executive") return <Navigate to="/exec" replace />;
  if (u.role === "feeder") return <Navigate to="/feeder/paths" replace />;
  if (u.role === "candidate") return <Navigate to="/candidate" replace />;
  return <Navigate to="/login" replace />;
}

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<HomeRedirect />} />
      <Route path="/login" element={<Login />} />

      <Route
        path="/exec"
        element={
          <ProtectedRoute roles={["executive"]}>
            <ExecDashboard />
          </ProtectedRoute>
        }
      />

      <Route
        path="/feeder/paths"
        element={
          <ProtectedRoute roles={["feeder", "executive"]}>
            <FeederPaths />
          </ProtectedRoute>
        }
      />
      <Route
        path="/feeder/paths/:id"
        element={
          <ProtectedRoute roles={["feeder", "executive"]}>
            <FeederPathEditor />
          </ProtectedRoute>
        }
      />
      <Route
        path="/feeder/candidates"
        element={
          <ProtectedRoute roles={["feeder", "executive"]}>
            <FeederCandidates />
          </ProtectedRoute>
        }
      />

      <Route
        path="/candidate"
        element={
          <ProtectedRoute roles={["candidate"]}>
            <CandidateHome />
          </ProtectedRoute>
        }
      />
      <Route
        path="/candidate/test/:assessmentId"
        element={
          <ProtectedRoute roles={["candidate"]}>
            <CandidateTest />
          </ProtectedRoute>
        }
      />
      <Route
        path="/candidate/chat/:sectionId"
        element={
          <ProtectedRoute roles={["candidate"]}>
            <CandidateChat />
          </ProtectedRoute>
        }
      />
      <Route
        path="/candidate/progress"
        element={
          <ProtectedRoute roles={["candidate"]}>
            <CandidateProgress />
          </ProtectedRoute>
        }
      />

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
