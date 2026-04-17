import { Link, useNavigate } from "react-router-dom";
import { getUser, clearUser } from "../auth.js";

const ROLE_LABEL = {
  executive: "Executive",
  feeder: "Feeder",
  candidate: "Candidate",
};

export default function Nav({ tabs = [] }) {
  const user = getUser();
  const navigate = useNavigate();

  function logout() {
    clearUser();
    navigate("/login", { replace: true });
  }

  return (
    <nav className="bg-white border-b border-gray-200 px-6 py-3 flex items-center justify-between">
      <div className="flex items-center gap-6">
        <Link to="/" className="text-xl font-bold text-indigo-600">
          PrepPath
        </Link>
        <div className="flex items-center gap-4">
          {tabs.map((t) => (
            <Link
              key={t.to}
              to={t.to}
              className="text-sm text-gray-600 hover:text-indigo-600 transition"
            >
              {t.label}
            </Link>
          ))}
        </div>
      </div>
      <div className="flex items-center gap-3 text-sm">
        {user && (
          <>
            <span className="text-gray-500">
              {user.name}{" "}
              <span className="text-xs text-gray-400">
                ({ROLE_LABEL[user.role] || user.role})
              </span>
            </span>
            <button
              onClick={logout}
              className="text-gray-400 hover:text-red-500 transition"
            >
              Logout
            </button>
          </>
        )}
      </div>
    </nav>
  );
}
