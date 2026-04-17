import { useEffect, useMemo, useState } from "react";
import Nav from "../../components/Nav.jsx";
import { api } from "../../api.js";

const CHANNELS = [
  { key: "foundation", label: "Foundation Training", color: "blue",
    desc: "Building core concepts" },
  { key: "deepdive", label: "Deep Dive", color: "purple",
    desc: "Trade-offs and design depth" },
  { key: "simulation", label: "Interview Ready", color: "green",
    desc: "In interview simulation" },
  { key: "improvement", label: "Improvement", color: "orange",
    desc: "Targeted remediation" },
  { key: "", label: "Not Started", color: "gray",
    desc: "No preliminary taken yet" },
];

const COLOR_MAP = {
  blue: { bg: "bg-blue-50", text: "text-blue-700", border: "border-blue-200", dot: "bg-blue-500", pill: "bg-blue-100 text-blue-700" },
  purple: { bg: "bg-purple-50", text: "text-purple-700", border: "border-purple-200", dot: "bg-purple-500", pill: "bg-purple-100 text-purple-700" },
  green: { bg: "bg-green-50", text: "text-green-700", border: "border-green-200", dot: "bg-green-500", pill: "bg-green-100 text-green-700" },
  orange: { bg: "bg-orange-50", text: "text-orange-700", border: "border-orange-200", dot: "bg-orange-500", pill: "bg-orange-100 text-orange-700" },
  gray: { bg: "bg-gray-50", text: "text-gray-600", border: "border-gray-200", dot: "bg-gray-400", pill: "bg-gray-100 text-gray-600" },
};

const LEVEL_STYLE = {
  junior: "bg-gray-100 text-gray-700",
  mid: "bg-indigo-100 text-indigo-700",
  senior: "bg-pink-100 text-pink-700",
};

export default function ExecDashboard() {
  const [candidates, setCandidates] = useState([]);
  const [paths, setPaths] = useState([]);
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);

  const [pathFilter, setPathFilter] = useState("all");
  const [channelFilter, setChannelFilter] = useState("all");
  const [search, setSearch] = useState("");

  useEffect(() => {
    (async () => {
      try {
        const [c, p, u] = await Promise.all([
          api.get("/candidates"),
          api.get("/pipelines"),
          api.get("/users"),
        ]);
        setCandidates(c.candidates || []);
        setPaths(p.pipelines || []);
        setUsers(u.users || []);
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const channelCounts = useMemo(() => {
    const acc = {};
    for (const c of candidates) acc[c.channel || ""] = (acc[c.channel || ""] || 0) + 1;
    return acc;
  }, [candidates]);

  const filtered = useMemo(() => {
    return candidates.filter((c) => {
      if (pathFilter !== "all") {
        if (pathFilter === "none" && c.learning_path_id) return false;
        if (pathFilter !== "none" && String(c.learning_path_id) !== pathFilter) return false;
      }
      if (channelFilter !== "all" && (c.channel || "") !== channelFilter) return false;
      if (search) {
        const q = search.toLowerCase();
        const hay = `${c.name} ${c.email} ${c.created_by_name || ""}`.toLowerCase();
        if (!hay.includes(q)) return false;
      }
      return true;
    });
  }, [candidates, pathFilter, channelFilter, search]);

  const stats = useMemo(() => {
    const total = candidates.length;
    const ready = candidates.filter((c) => c.interview_ready).length;
    const training = candidates.filter(
      (c) => c.channel && c.channel !== "simulation"
    ).length;
    const notStarted = candidates.filter((c) => !c.channel).length;
    return { total, ready, training, notStarted };
  }, [candidates]);

  return (
    <div className="min-h-screen">
      <Nav
        tabs={[
          { to: "/exec", label: "Overview" },
          { to: "/feeder/paths", label: "Learning Paths" },
          { to: "/feeder/candidates", label: "Candidates" },
        ]}
      />
      <div className="max-w-7xl mx-auto px-6 py-8">
        <h1 className="text-2xl font-bold text-gray-800 mb-1">
          Candidate Overview
        </h1>
        <p className="text-sm text-gray-500 mb-6">
          Where every candidate currently stands across the organisation.
        </p>

        {loading ? (
          <p className="text-gray-500">Loading…</p>
        ) : (
          <>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
              <Stat label="Total candidates" value={stats.total} />
              <Stat label="Interview ready" value={stats.ready} accent="green" />
              <Stat label="In training" value={stats.training} accent="blue" />
              <Stat label="Awaiting assessment" value={stats.notStarted} accent="gray" />
            </div>

            <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wide mb-3">
              By training stage
            </h2>
            <div className="grid grid-cols-1 md:grid-cols-5 gap-3 mb-8">
              {CHANNELS.map((ch) => {
                const count = channelCounts[ch.key] || 0;
                const color = COLOR_MAP[ch.color];
                const active = channelFilter === ch.key;
                return (
                  <button
                    key={ch.key}
                    onClick={() =>
                      setChannelFilter(active ? "all" : ch.key)
                    }
                    className={`text-left rounded-2xl border p-4 transition ${
                      active
                        ? `${color.bg} ${color.border} ring-2 ring-offset-1`
                        : `bg-white border-gray-200 hover:${color.border}`
                    }`}
                  >
                    <div className="flex items-center gap-2 mb-2">
                      <span className={`w-2 h-2 rounded-full ${color.dot}`} />
                      <p className={`text-xs font-semibold uppercase tracking-wide ${color.text}`}>
                        {ch.label}
                      </p>
                    </div>
                    <p className="text-3xl font-bold text-gray-800">{count}</p>
                    <p className="text-xs text-gray-400 mt-1">{ch.desc}</p>
                  </button>
                );
              })}
            </div>

            <div className="bg-white rounded-2xl shadow p-5 mb-4">
              <div className="flex flex-wrap items-center gap-3">
                <div className="flex-1 min-w-[200px]">
                  <label className="block text-xs font-semibold text-gray-500 mb-1">
                    Search
                  </label>
                  <input
                    type="text"
                    placeholder="Name, email, or creator…"
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                    className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm"
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-gray-500 mb-1">
                    Learning path
                  </label>
                  <select
                    value={pathFilter}
                    onChange={(e) => setPathFilter(e.target.value)}
                    className="border border-gray-200 rounded-lg px-3 py-2 text-sm min-w-[200px]"
                  >
                    <option value="all">All paths</option>
                    <option value="none">— not assigned —</option>
                    {paths.map((p) => (
                      <option key={p.id} value={String(p.id)}>
                        {p.name}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-xs font-semibold text-gray-500 mb-1">
                    Channel
                  </label>
                  <select
                    value={channelFilter}
                    onChange={(e) => setChannelFilter(e.target.value)}
                    className="border border-gray-200 rounded-lg px-3 py-2 text-sm min-w-[180px]"
                  >
                    <option value="all">All channels</option>
                    {CHANNELS.map((ch) => (
                      <option key={ch.key} value={ch.key}>
                        {ch.label}
                      </option>
                    ))}
                  </select>
                </div>
                {(pathFilter !== "all" ||
                  channelFilter !== "all" ||
                  search) && (
                  <button
                    onClick={() => {
                      setPathFilter("all");
                      setChannelFilter("all");
                      setSearch("");
                    }}
                    className="text-xs text-gray-500 hover:text-gray-800 underline"
                  >
                    Clear
                  </button>
                )}
              </div>
            </div>

            <div className="bg-white rounded-2xl shadow overflow-hidden">
              <div className="px-5 py-3 border-b border-gray-100 flex items-center justify-between">
                <h3 className="font-semibold text-gray-800">
                  Candidates{" "}
                  <span className="text-sm text-gray-400 font-normal">
                    ({filtered.length})
                  </span>
                </h3>
              </div>
              <CandidatesTable candidates={filtered} />
            </div>

            <div className="mt-8 grid grid-cols-1 md:grid-cols-2 gap-4">
              <LearningPathsCard paths={paths} candidates={candidates} />
              <TeamCard users={users} />
            </div>
          </>
        )}
      </div>
    </div>
  );
}

function Stat({ label, value, accent }) {
  const accentColor = {
    green: "text-green-600",
    blue: "text-blue-600",
    gray: "text-gray-500",
  }[accent] || "text-gray-800";
  return (
    <div className="bg-white rounded-2xl shadow p-5">
      <p className="text-xs font-semibold text-gray-400 uppercase tracking-wide">
        {label}
      </p>
      <p className={`text-3xl font-bold mt-1 ${accentColor}`}>{value}</p>
    </div>
  );
}

function CandidatesTable({ candidates }) {
  if (candidates.length === 0) {
    return (
      <p className="text-sm text-gray-400 px-5 py-8 text-center">
        No candidates match the current filters.
      </p>
    );
  }
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead className="bg-gray-50">
          <tr className="text-left text-xs text-gray-500 uppercase tracking-wide">
            <Th>Candidate</Th>
            <Th>Channel</Th>
            <Th>Learning path</Th>
            <Th>Path seniority</Th>
            <Th>Created by</Th>
            <Th>Status</Th>
          </tr>
        </thead>
        <tbody>
          {candidates.map((c) => (
            <tr key={c.id} className="border-t border-gray-100">
              <Td>
                <div>
                  <p className="font-medium text-gray-800">{c.name || "—"}</p>
                  <p className="text-xs text-gray-400">{c.email}</p>
                </div>
              </Td>
              <Td>
                <ChannelPill channel={c.channel} />
              </Td>
              <Td>
                {c.learning_path_name ? (
                  <span className="text-gray-700">{c.learning_path_name}</span>
                ) : (
                  <span className="text-xs text-gray-400">not assigned</span>
                )}
              </Td>
              <Td>
                <span className="text-xs text-gray-600 capitalize">
                  {c.learning_path_seniority || "—"}
                </span>
              </Td>
              <Td>
                {c.created_by_name ? (
                  <div>
                    <p className="text-gray-700">{c.created_by_name}</p>
                    <p className="text-xs text-gray-400 capitalize">
                      {c.created_by_role}
                    </p>
                  </div>
                ) : (
                  <span className="text-xs text-gray-400">system / seed</span>
                )}
              </Td>
              <Td>
                {c.interview_ready ? (
                  <span className="text-xs bg-green-100 text-green-700 px-2 py-0.5 rounded-full">
                    ✓ interview ready
                  </span>
                ) : c.channel === "improvement" ? (
                  <span className="text-xs bg-orange-100 text-orange-700 px-2 py-0.5 rounded-full">
                    on remediation
                  </span>
                ) : c.channel ? (
                  <span className="text-xs bg-gray-100 text-gray-600 px-2 py-0.5 rounded-full">
                    in training
                  </span>
                ) : (
                  <span className="text-xs bg-yellow-100 text-yellow-700 px-2 py-0.5 rounded-full">
                    pending prelim
                  </span>
                )}
              </Td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ChannelPill({ channel }) {
  const match = CHANNELS.find((c) => c.key === (channel || ""));
  const color = COLOR_MAP[match?.color || "gray"];
  return (
    <span className={`text-xs px-2 py-0.5 rounded-full ${color.pill}`}>
      {match?.label || "—"}
    </span>
  );
}

function Th({ children }) {
  return <th className="py-3 px-5 font-semibold">{children}</th>;
}
function Td({ children }) {
  return <td className="py-3 px-5 align-top">{children}</td>;
}

function LearningPathsCard({ paths, candidates }) {
  const perPath = useMemo(() => {
    const acc = {};
    for (const c of candidates) {
      if (!c.learning_path_id) continue;
      acc[c.learning_path_id] = (acc[c.learning_path_id] || 0) + 1;
    }
    return acc;
  }, [candidates]);

  return (
    <div className="bg-white rounded-2xl shadow p-5">
      <h3 className="font-semibold text-gray-800 mb-3">Learning paths</h3>
      {paths.length === 0 ? (
        <p className="text-sm text-gray-400">No learning paths defined yet.</p>
      ) : (
        <div className="space-y-2">
          {paths.map((p) => (
            <div
              key={p.id}
              className="flex items-center justify-between bg-gray-50 rounded-xl p-3"
            >
              <div>
                <p className="font-medium text-gray-800">{p.name}</p>
                <p className="text-xs text-gray-400 capitalize">
                  {p.seniority}
                  {p.language ? ` · ${p.language}` : ""}
                </p>
              </div>
              <div className="text-right">
                <p className="text-sm font-semibold text-gray-700">
                  {perPath[p.id] || 0}{" "}
                  <span className="text-xs text-gray-400 font-normal">
                    candidates
                  </span>
                </p>
                <span
                  className={`text-xs px-2 py-0.5 rounded-full ${
                    p.status === "published"
                      ? "bg-green-100 text-green-700"
                      : "bg-gray-200 text-gray-600"
                  }`}
                >
                  {p.status}
                </span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function TeamCard({ users }) {
  const feeders = users.filter((u) => u.role === "feeder");
  const execs = users.filter((u) => u.role === "executive");
  return (
    <div className="bg-white rounded-2xl shadow p-5">
      <h3 className="font-semibold text-gray-800 mb-3">Team</h3>
      <Section label="Executives" users={execs} />
      <Section label="Feeders" users={feeders} />
    </div>
  );
}

function Section({ label, users }) {
  if (users.length === 0) return null;
  return (
    <div className="mb-3 last:mb-0">
      <p className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-2">
        {label}
      </p>
      <div className="space-y-1">
        {users.map((u) => (
          <div
            key={u.id}
            className="flex items-center justify-between text-sm"
          >
            <span className="text-gray-700">{u.name}</span>
            <span className="text-xs text-gray-400">{u.email}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
