import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import Nav from "../../components/Nav.jsx";
import { api } from "../../api.js";

export default function PathEditor() {
  const { id } = useParams();
  const [path, setPath] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [publishing, setPublishing] = useState(false);

  async function refresh() {
    const data = await api.get(`/pipelines/${id}`);
    setPath(data);
  }

  useEffect(() => {
    refresh().finally(() => setLoading(false));
  }, [id]);

  async function publish() {
    if (!confirm("Publish this path? This runs the Question Gen agent on every section and may take a minute.")) return;
    setPublishing(true);
    setError("");
    try {
      await api.post(`/pipelines/${id}/publish`);
      await refresh();
    } catch (err) {
      setError(err.message);
    } finally {
      setPublishing(false);
    }
  }

  if (loading) return <Shell><p>Loading…</p></Shell>;
  if (!path) return <Shell><p>Path not found.</p></Shell>;

  return (
    <Shell>
      <Link to="/feeder/paths" className="text-sm text-gray-400 hover:text-gray-600">
        ← Back to paths
      </Link>
      <div className="flex items-start justify-between mt-2 mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-800">{path.name}</h1>
          <p className="text-sm text-gray-500 mt-1">{path.description}</p>
          <div className="flex gap-2 mt-2 text-xs">
            <span className="bg-gray-100 text-gray-600 px-2 py-0.5 rounded-full">
              {path.seniority}
            </span>
            {path.language && (
              <span className="bg-gray-100 text-gray-600 px-2 py-0.5 rounded-full">
                {path.language}
              </span>
            )}
            <span
              className={`px-2 py-0.5 rounded-full ${
                path.status === "published"
                  ? "bg-green-100 text-green-700"
                  : "bg-gray-100 text-gray-600"
              }`}
            >
              {path.status}
            </span>
          </div>
        </div>
        {path.status !== "published" && (
          <button
            onClick={publish}
            disabled={publishing}
            className="bg-green-500 hover:bg-green-600 disabled:bg-gray-300 text-white font-semibold px-4 py-2 rounded-lg text-sm transition"
          >
            {publishing ? "Publishing…" : "Publish"}
          </button>
        )}
      </div>

      {error && (
        <div className="bg-red-50 text-red-600 text-sm px-3 py-2 rounded-lg mb-4">
          {error}
        </div>
      )}

      <SectionsBlock path={path} onChange={refresh} />
      <AddSection pipelineId={id} onAdded={refresh} />
    </Shell>
  );
}

function SectionsBlock({ path, onChange }) {
  if (path.sections.length === 0)
    return (
      <div className="bg-white rounded-2xl shadow p-5 mb-4 text-sm text-gray-500">
        No sections yet. Add one below.
      </div>
    );
  return (
    <div className="space-y-4 mb-4">
      {path.sections.map((s) => (
        <SectionCard key={s.id} section={s} onChange={onChange} />
      ))}
    </div>
  );
}

function SectionCard({ section, onChange }) {
  const [showPattern, setShowPattern] = useState(false);
  const [pat, setPat] = useState({ name: "", description: "" });
  const [editing, setEditing] = useState(false);
  const [editForm, setEditForm] = useState({
    name: section.name,
    description: section.description || "",
    concepts: section.concepts.join(", "),
    sample_questions: (section.sample_questions || []).join("\n"),
  });
  const [editError, setEditError] = useState("");

  async function addPattern(e) {
    e.preventDefault();
    await api.post(`/pipelines/sections/${section.id}/patterns`, pat);
    setPat({ name: "", description: "" });
    setShowPattern(false);
    onChange();
  }

  async function saveEdit(e) {
    e.preventDefault();
    setEditError("");
    try {
      await api.put(`/pipelines/sections/${section.id}`, {
        name: editForm.name,
        description: editForm.description,
        concepts: editForm.concepts.split(",").map((s) => s.trim()).filter(Boolean),
        sample_questions: editForm.sample_questions.split("\n").map((s) => s.trim()).filter(Boolean),
      });
      setEditing(false);
      onChange();
    } catch (err) {
      setEditError(err.message);
    }
  }

  if (editing) {
    return (
      <div className="bg-white rounded-2xl shadow p-5">
        <p className="text-sm font-semibold text-gray-700 mb-3">Edit section</p>
        <form onSubmit={saveEdit} className="space-y-2">
          <input
            type="text"
            required
            placeholder="Section name"
            value={editForm.name}
            onChange={(e) => setEditForm({ ...editForm, name: e.target.value })}
            className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm"
          />
          <input
            type="text"
            placeholder="Description"
            value={editForm.description}
            onChange={(e) => setEditForm({ ...editForm, description: e.target.value })}
            className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm"
          />
          <input
            type="text"
            placeholder="Concept tags (comma-separated)"
            value={editForm.concepts}
            onChange={(e) => setEditForm({ ...editForm, concepts: e.target.value })}
            className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm"
          />
          <div>
            <label className="block text-xs font-medium text-gray-500 mb-1">
              Sample questions <span className="font-normal text-gray-400">(one per line)</span>
            </label>
            <textarea
              rows={4}
              value={editForm.sample_questions}
              onChange={(e) => setEditForm({ ...editForm, sample_questions: e.target.value })}
              className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm resize-y"
            />
          </div>
          {editError && (
            <div className="text-red-600 text-sm bg-red-50 px-3 py-2 rounded-lg">{editError}</div>
          )}
          <div className="flex gap-2">
            <button
              type="submit"
              className="bg-indigo-500 hover:bg-indigo-600 text-white text-sm px-3 py-1.5 rounded-lg"
            >
              Save
            </button>
            <button
              type="button"
              onClick={() => setEditing(false)}
              className="text-sm text-gray-500 hover:text-gray-700 px-3 py-1.5 rounded-lg border border-gray-200"
            >
              Cancel
            </button>
          </div>
        </form>
      </div>
    );
  }

  return (
    <div className="bg-white rounded-2xl shadow p-5">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="font-semibold text-gray-800">{section.name}</h3>
          <p className="text-xs text-gray-500 mt-1">{section.description}</p>
        </div>
        <button
          onClick={() => setEditing(true)}
          className="text-xs text-gray-400 hover:text-indigo-600 border border-gray-200 hover:border-indigo-300 px-2.5 py-1 rounded-lg transition"
        >
          Edit
        </button>
      </div>
      <div className="mt-3 flex flex-wrap gap-1.5">
        {section.concepts.map((c) => (
          <span
            key={c}
            className="text-xs bg-indigo-50 text-indigo-700 px-2 py-0.5 rounded-full"
          >
            {c}
          </span>
        ))}
      </div>

      {section.sample_questions?.length > 0 && (
        <div className="mt-3 border-t border-gray-100 pt-3">
          <p className="text-xs font-semibold text-gray-400 uppercase mb-2">
            Sample questions{" "}
            <span className="normal-case font-normal text-gray-400">
              — tagged &amp; saved on publish
            </span>
          </p>
          <ul className="space-y-1 text-xs text-gray-600">
            {section.sample_questions.map((q, i) => (
              <li key={i} className="bg-gray-50 rounded-lg px-2 py-1">
                {q}
              </li>
            ))}
          </ul>
        </div>
      )}

      {section.patterns.length > 0 && (
        <div className="mt-3 border-t border-gray-100 pt-3">
          <p className="text-xs font-semibold text-gray-400 uppercase mb-2">
            Patterns
          </p>
          <ul className="space-y-1 text-sm text-gray-700">
            {section.patterns.map((p) => (
              <li key={p.id}>• {p.name}</li>
            ))}
          </ul>
        </div>
      )}

      <div className="mt-3">
        <button
          onClick={() => setShowPattern((v) => !v)}
          className="text-xs text-indigo-500 hover:text-indigo-700"
        >
          {showPattern ? "Cancel" : "+ Add pattern"}
        </button>
      </div>

      {showPattern && (
        <form onSubmit={addPattern} className="mt-2 space-y-2">
          <input
            type="text"
            placeholder="Pattern name"
            required
            value={pat.name}
            onChange={(e) => setPat({ ...pat, name: e.target.value })}
            className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm"
          />
          <input
            type="text"
            placeholder="Description"
            value={pat.description}
            onChange={(e) => setPat({ ...pat, description: e.target.value })}
            className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm"
          />
          <button className="bg-indigo-500 hover:bg-indigo-600 text-white text-sm px-3 py-1.5 rounded-lg">
            Save pattern
          </button>
        </form>
      )}
    </div>
  );
}

function AddSection({ pipelineId, onAdded }) {
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({
    name: "",
    description: "",
    concepts: "",
    sample_questions: "",
  });
  const [error, setError] = useState("");

  async function submit(e) {
    e.preventDefault();
    setError("");
    try {
      await api.post(`/pipelines/${pipelineId}/sections`, {
        name: form.name,
        description: form.description,
        concepts: form.concepts
          .split(",")
          .map((s) => s.trim())
          .filter(Boolean),
        sample_questions: form.sample_questions
          .split("\n")
          .map((s) => s.trim())
          .filter(Boolean),
      });
      setForm({ name: "", description: "", concepts: "", sample_questions: "" });
      setOpen(false);
      onAdded();
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <div className="bg-white rounded-2xl shadow p-5">
      <button
        onClick={() => setOpen((v) => !v)}
        className="text-sm font-semibold text-indigo-500 hover:text-indigo-700"
      >
        {open ? "Cancel" : "+ Add section"}
      </button>
      {open && (
        <form onSubmit={submit} className="mt-3 space-y-2">
          <input
            type="text"
            placeholder="Section name"
            required
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
            className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm"
          />
          <input
            type="text"
            placeholder="Description"
            value={form.description}
            onChange={(e) => setForm({ ...form, description: e.target.value })}
            className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm"
          />
          <input
            type="text"
            placeholder="Concept tags (comma-separated, e.g. python_types, python_oop)"
            value={form.concepts}
            onChange={(e) => setForm({ ...form, concepts: e.target.value })}
            className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm"
          />
          <div>
            <label className="block text-xs font-medium text-gray-500 mb-1">
              Sample questions{" "}
              <span className="font-normal text-gray-400">
                (one per line — the AI will tag and save these, then use them as style
                examples when generating the full question bank)
              </span>
            </label>
            <textarea
              rows={5}
              placeholder={"What is the difference between a list and a tuple in Python?\nYou are designing a caching layer — how would you choose between Redis and Memcached?\nExplain how Python's GIL affects multi-threaded programs."}
              value={form.sample_questions}
              onChange={(e) => setForm({ ...form, sample_questions: e.target.value })}
              className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm resize-y"
            />
          </div>
          {error && (
            <div className="text-red-600 text-sm bg-red-50 px-3 py-2 rounded-lg">
              {error}
            </div>
          )}
          <button className="bg-indigo-500 hover:bg-indigo-600 text-white text-sm px-3 py-1.5 rounded-lg">
            Save section
          </button>
        </form>
      )}
    </div>
  );
}

function Shell({ children }) {
  return (
    <div className="min-h-screen">
      <Nav
        tabs={[
          { to: "/feeder/paths", label: "Learning Paths" },
          { to: "/feeder/candidates", label: "Candidates" },
        ]}
      />
      <div className="max-w-4xl mx-auto px-6 py-8">{children}</div>
    </div>
  );
}
