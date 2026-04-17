import { useEffect, useState } from "react";
import Nav from "../../components/Nav.jsx";
import { api } from "../../api.js";
import { getUser } from "../../auth.js";

const CHANNEL_STYLE = {
  foundation: "bg-blue-100 text-blue-700",
  deepdive: "bg-purple-100 text-purple-700",
  simulation: "bg-green-100 text-green-700",
  improvement: "bg-orange-100 text-orange-700",
  "": "bg-gray-100 text-gray-500",
};

export default function Candidates() {
  const [candidates, setCandidates] = useState([]);
  const [paths, setPaths] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);

  async function refresh() {
    const [c, p] = await Promise.all([
      api.get("/candidates"),
      api.get("/pipelines"),
    ]);
    setCandidates(c.candidates || []);
    setPaths(p.pipelines || []);
  }

  useEffect(() => {
    refresh().finally(() => setLoading(false));
  }, []);

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
            <h1 className="text-2xl font-bold text-gray-800">Candidates</h1>
            <p className="text-sm text-gray-500">
              Create new candidates and assign them to a learning path.
            </p>
          </div>
          <button
            onClick={() => setShowCreate((v) => !v)}
            className="bg-indigo-500 hover:bg-indigo-600 text-white font-semibold px-4 py-2 rounded-lg text-sm transition"
          >
            {showCreate ? "Cancel" : "+ New Candidate"}
          </button>
        </div>

        {showCreate && (
          <CreateCandidate
            onCreated={() => {
              setShowCreate(false);
              refresh();
            }}
          />
        )}

        {loading ? (
          <p className="text-gray-500">Loading…</p>
        ) : candidates.length === 0 ? (
          <div className="bg-white rounded-2xl shadow p-8 text-center text-gray-500">
            No candidates yet.
          </div>
        ) : (
          <div className="grid gap-3">
            {candidates.map((c) => (
              <CandidateRow
                key={c.id}
                candidate={c}
                paths={paths}
                onAssigned={refresh}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function CreateCandidate({ onCreated }) {
  const [form, setForm] = useState({ name: "", email: "", password: "" });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const currentUser = getUser();

  async function submit(e) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      await api.post("/users", {
        ...form,
        role: "candidate",
        created_by_user_id: currentUser?.id ?? null,
      });
      setForm({ name: "", email: "", password: "" });
      onCreated();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form
      onSubmit={submit}
      className="bg-white rounded-2xl shadow p-5 mb-6 grid grid-cols-1 md:grid-cols-4 gap-3"
    >
      <input
        required
        placeholder="Name"
        value={form.name}
        onChange={(e) => setForm({ ...form, name: e.target.value })}
        className="border border-gray-200 rounded-lg px-3 py-2 text-sm"
      />
      <input
        type="email"
        required
        placeholder="Email"
        value={form.email}
        onChange={(e) => setForm({ ...form, email: e.target.value })}
        className="border border-gray-200 rounded-lg px-3 py-2 text-sm"
      />
      <input
        type="password"
        required
        placeholder="Password"
        value={form.password}
        onChange={(e) => setForm({ ...form, password: e.target.value })}
        className="border border-gray-200 rounded-lg px-3 py-2 text-sm"
      />
      <button
        disabled={busy}
        className="bg-indigo-500 hover:bg-indigo-600 disabled:bg-gray-300 text-white font-semibold text-sm rounded-lg"
      >
        {busy ? "Creating…" : "Create"}
      </button>
      {error && (
        <div className="md:col-span-4 text-red-600 text-sm bg-red-50 px-3 py-2 rounded-lg">
          {error}
        </div>
      )}
    </form>
  );
}

function CandidateRow({ candidate, paths, onAssigned }) {
  const [pathId, setPathId] = useState(candidate.learning_path_id || "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function assign() {
    if (!pathId) return;
    if (
      candidate.learning_path_id &&
      !confirm("Reassigning will reset this candidate's progress. Continue?")
    )
      return;
    setBusy(true);
    setError("");
    try {
      await api.put(`/candidates/${candidate.id}/pipeline`, {
        learning_path_id: parseInt(pathId),
      });
      onAssigned();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="bg-white rounded-2xl shadow p-5">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <p className="font-semibold text-gray-800">{candidate.name}</p>
          <p className="text-xs text-gray-400">{candidate.email}</p>
        </div>
        <div className="flex items-center gap-2 text-xs">
          <span
            className={`px-2 py-0.5 rounded-full ${
              CHANNEL_STYLE[candidate.channel || ""]
            }`}
          >
            {candidate.channel || "not started"}
          </span>
          {candidate.interview_ready && (
            <span className="bg-green-100 text-green-700 px-2 py-0.5 rounded-full">
              interview ready
            </span>
          )}
        </div>
      </div>

      <div className="mt-3 flex items-center gap-2">
        <select
          value={pathId || ""}
          onChange={(e) => setPathId(e.target.value)}
          className="border border-gray-200 rounded-lg px-3 py-2 text-sm flex-1"
        >
          <option value="">— select a learning path —</option>
          {paths.map((p) => (
            <option
              key={p.id}
              value={p.id}
              disabled={p.status !== "published"}
            >
              {p.name}
              {p.status !== "published" ? ` (${p.status})` : ""}
            </option>
          ))}
        </select>
        <button
          onClick={assign}
          disabled={!pathId || busy}
          className="bg-indigo-500 hover:bg-indigo-600 disabled:bg-gray-300 text-white font-semibold px-4 py-2 rounded-lg text-sm transition"
        >
          {busy ? "Assigning…" : "Assign"}
        </button>
      </div>

      {error && (
        <div className="mt-2 text-red-600 text-sm bg-red-50 px-3 py-2 rounded-lg">
          {error}
        </div>
      )}

      {candidate.gaps?.length > 0 && (
        <div className="mt-3 text-xs text-gray-500">
          <span className="font-semibold text-gray-400 uppercase tracking-wide">
            Gaps:{" "}
          </span>
          {candidate.gaps.join(", ")}
        </div>
      )}
    </div>
  );
}
