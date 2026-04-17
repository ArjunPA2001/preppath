import { Navigate } from "react-router-dom";
import { getUser } from "../auth.js";

export default function ProtectedRoute({ roles, children }) {
  const user = getUser();
  if (!user) return <Navigate to="/login" replace />;
  if (roles && !roles.includes(user.role)) {
    return <Navigate to="/" replace />;
  }
  return children;
}
