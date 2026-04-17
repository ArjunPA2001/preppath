import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import Nav from "../../components/Nav.jsx";
import { api } from "../../api.js";

export default function FeederPaths() {
  const [paths, setPaths] = useState([]);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({
    name: "",
    description: "",
    seniority: "mid",
    language: "",
  });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  async function refresh() {
    const data = await api.get("/pipelines");
    setPaths(data.pipelines || []);
  }

  useEffect(() => {
    refresh().finally(() => setLoading(false));
  }, []);

  async function create(e) {
    e.preventDefault();
    setError("");
    try {
      await api.post("/pipelines", form);
      setForm({ name: "", description: "", seniority: "mid", language: "" });
      setShowForm(false);
      refresh();
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <div className="min-h-screen">
      <Nav
        tabs={[
          { to: "/feeder/paths", label: "Learning Paths" },
          { to: "/feeder/candidates", label: "Candidates" },
        ]}
      />
      <div className="max-w-5xl mx-auto px-6 py-8">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-2xl font-bold text-gray-800">Learning Paths</h1>
            <p className="text-sm text-gray-500">
              Build, publish, and manage evaluation pipelines.
            </p>
          </div>
          <button
            onClick={() => setShowForm((v) => !v)}
            className="bg-indigo-500 hover:bg-indigo-600 text-white font-semibold px-4 py-2 rounded-lg text-sm transition"
          >
            {showForm ? "Cancel" : "+ New Path"}
          </button>
        </div>

        {showForm && (
          <form
            onSubmit={create}
            className="bg-white rounded-2xl shadow p-5 mb-6 space-y-3"
          >
            <Field
              label="Name"
              value={form.name}
              onChange={(v) => setForm({ ...form, name: v })}
              required
            />
            <Field
              label="Description"
              value={form.description}
              onChange={(v) => setForm({ ...form, description: v })}
            />
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-xs font-semibold text-gray-500 mb-1">
                  Seniority
                </label>
                <select
                  value={form.seniority}
                  onChange={(e) =>
                    setForm({ ...form, seniority: e.target.value })
                  }
                  className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm"
                >
                  <option value="junior">Junior</option>
                  <option value="mid">Mid</option>
                  <option value="senior">Senior</option>
                </select>
              </div>
              <Field
                label="Language"
                value={form.language}
                onChange={(v) => setForm({ ...form, language: v })}
              />
            </div>
            {error && (
              <div className="text-red-600 text-sm bg-red-50 px-3 py-2 rounded-lg">
                {error}
              </div>
            )}
            <button
              type="submit"
              className="bg-indigo-500 hover:bg-indigo-600 text-white font-semibold px-4 py-2 rounded-lg text-sm transition"
            >
              Create path
            </button>
          </form>
        )}

        {loading ? (
          <p className="text-gray-500">Loading…</p>
        ) : paths.length === 0 ? (
          <div className="bg-white rounded-2xl shadow p-8 text-center text-gray-500">
            No paths yet. Create your first one.
          </div>
        ) : (
          <div className="grid gap-3">
            {paths.map((p) => (
              <Link
                key={p.id}
                to={`/feeder/paths/${p.id}`}
                className="bg-white rounded-2xl shadow p-5 hover:shadow-md transition flex items-center justify-between"
              >
                <div>
                  <p className="font-semibold text-gray-800">{p.name}</p>
                  <p className="text-xs text-gray-400 mt-1">
                    {p.seniority}
                    {p.language ? ` · ${p.language}` : ""}
                  </p>
                </div>
                <span
                  className={`text-xs px-3 py-1 rounded-full ${
                    p.status === "published"
                      ? "bg-green-100 text-green-700"
                      : "bg-gray-100 text-gray-600"
                  }`}
                >
                  {p.status}
                </span>
              </Link>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function Field({ label, value, onChange, required }) {
  return (
    <div>
      <label className="block text-xs font-semibold text-gray-500 mb-1">
        {label}
      </label>
      <input
        type="text"
        required={required}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300"
      />
    </div>
  );
}
