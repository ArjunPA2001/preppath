import { useEffect, useState } from "react";
import Nav from "../../components/Nav.jsx";
import { api } from "../../api.js";
import { getUser } from "../../auth.js";
import { Link } from "react-router-dom";

const CHANNEL_STYLE = {
  foundation: "bg-blue-100 text-blue-700",
  deepdive: "bg-purple-100 text-purple-700",
  simulation: "bg-green-100 text-green-700",
  improvement: "bg-orange-100 text-orange-700",
  "": "bg-gray-100 text-gray-500",
};

export default function CandidateProgress() {
  const user = getUser();
  const candidateId = user?.candidate?.id;
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    (async () => {
      if (!candidateId) {
        setError("Missing candidate profile.");
        setLoading(false);
        return;
      }
      try {
        const res = await api.get(`/candidates/${candidateId}/progress`);
        setData(res);
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    })();
  }, [candidateId]);

  return (
    <div className="min-h-screen">
      <Nav
        tabs={[
          { to: "/candidate", label: "Home" },
          { to: "/candidate/progress", label: "Progress" },
        ]}
      />
      <div className="max-w-3xl mx-auto px-4 py-8">
        <h1 className="text-2xl font-bold text-gray-800 mb-1">Your Progress</h1>
        <p className="text-sm text-gray-500 mb-6">
          Channel, sections, and concepts covered.
        </p>

        {loading ? (
          <p className="text-gray-500">Loading…</p>
        ) : error ? (
          <div className="bg-red-50 text-red-700 p-4 rounded-xl">{error}</div>
        ) : (
          <>
            <div className="bg-white rounded-2xl shadow p-6 mb-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-xs font-semibold text-gray-400 uppercase">
                    Channel
                  </p>
                  <p className="mt-1">
                    <span
                      className={`px-3 py-1 rounded-full text-sm font-semibold ${
                        CHANNEL_STYLE[data.candidate.channel || ""]
                      }`}
                    >
                      {data.candidate.channel || "not started"}
                    </span>
                  </p>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4 mt-4">
                <TagList
                  label="Gaps"
                  items={data.candidate.gaps || []}
                  color="red"
                />
                <TagList
                  label="Strengths"
                  items={data.candidate.strengths || []}
                  color="green"
                />
              </div>
            </div>

            <div className="bg-white rounded-2xl shadow p-6 mb-4">
              <h2 className="font-semibold text-gray-800 mb-3">Sections</h2>
              {data.sections.length === 0 ? (
                <p className="text-sm text-gray-400">No sections.</p>
              ) : (
                <div className="space-y-2">
                  {data.sections.map((s) => {
                    const done = data.completed_section_ids.includes(s.id);
                    return (
                      <div
                        key={s.id}
                        className="flex items-center justify-between bg-gray-50 rounded-xl p-3"
                      >
                        <div>
                          <p className="font-medium text-gray-700">{s.name}</p>
                          <p className="text-xs text-gray-400">
                            {s.concepts.join(" · ")}
                          </p>
                        </div>
                        <span
                          className={`text-xs px-2 py-1 rounded-full ${
                            done
                              ? "bg-green-100 text-green-700"
                              : "bg-gray-200 text-gray-500"
                          }`}
                        >
                          {done ? "✓ Done" : "In progress"}
                        </span>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>

            {data.active_session && (
              <div className="bg-white rounded-2xl shadow p-6 border-l-4 border-indigo-400">
                <h2 className="font-semibold text-gray-800 mb-2">
                  Active session
                </h2>
                <p className="text-sm text-gray-500 mb-3">
                  You have an in-progress mentor session.
                </p>
                <Link
                  to={`/candidate/chat/${data.active_session.section_id}`}
                  className="inline-block bg-indigo-500 hover:bg-indigo-600 text-white font-semibold px-4 py-2 rounded-lg text-sm transition"
                >
                  Resume →
                </Link>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}

function TagList({ label, items, color }) {
  const style =
    color === "red"
      ? "bg-red-100 text-red-700"
      : "bg-green-100 text-green-700";
  const labelStyle = color === "red" ? "text-red-500" : "text-green-600";
  return (
    <div>
      <p
        className={`text-xs font-semibold uppercase tracking-wide mb-2 ${labelStyle}`}
      >
        {label}
      </p>
      <div className="flex flex-wrap gap-2">
        {items.length === 0 && (
          <span className="text-xs text-gray-400">—</span>
        )}
        {items.map((s) => (
          <span
            key={s}
            className={`text-xs px-2 py-1 rounded-full ${style}`}
          >
            {s.replace(/_/g, " ")}
          </span>
        ))}
      </div>
    </div>
  );
}
