import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import Nav from "../../components/Nav.jsx";
import { api } from "../../api.js";
import { getUser, setUser } from "../../auth.js";

const CHANNEL_STYLE = {
  foundation: "bg-blue-100 text-blue-700",
  deepdive: "bg-purple-100 text-purple-700",
  simulation: "bg-green-100 text-green-700",
  improvement: "bg-orange-100 text-orange-700",
  "": "bg-gray-100 text-gray-500",
};

export default function CandidateHome() {
  const user = getUser();
  const navigate = useNavigate();
  const [candidate, setCandidate] = useState(user?.candidate || null);
  const [progress, setProgress] = useState(null);
  const [preliminaryId, setPreliminaryId] = useState(null);
  const [advancing, setAdvancing] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    (async () => {
      try {
        const fresh = await api.get(`/users/${user.id}`);
        setUser(fresh);
        setCandidate(fresh.candidate);
        if (fresh.candidate?.id) {
          const prog = await api.get(
            `/candidates/${fresh.candidate.id}/progress`
          );
          setProgress(prog);
        }
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  async function startPreliminary() {
    if (!candidate?.id) return;
    try {
      const res = await api.post("/assessments", {
        candidate_id: candidate.id,
        assessment_type: "preliminary_test",
      });
      setPreliminaryId(res.assessment_id);
    } catch (err) {
      setError(err.message);
    }
  }

  async function startAdvancement() {
    if (!candidate?.id || advancing) return;
    setAdvancing(true);
    setError("");
    try {
      const res = await api.post("/assessments", {
        candidate_id: candidate.id,
        assessment_type: "topic_gate",
      });
      navigate(`/candidate/test/${res.assessment_id}?type=topic_gate`);
    } catch (err) {
      setError(err.message);
      setAdvancing(false);
    }
  }

  if (loading)
    return (
      <Shell>
        <p className="text-gray-500">Loading…</p>
      </Shell>
    );

  if (!candidate) {
    return (
      <Shell>
        <div className="bg-white rounded-2xl shadow p-6">
          <p className="text-gray-700">
            Your candidate profile is not set up yet. Please contact your
            administrator.
          </p>
          {error && (
            <p className="mt-2 text-red-600 text-sm">{error}</p>
          )}
        </div>
      </Shell>
    );
  }

  const needsPath = !candidate.learning_path_id;
  const needsPrelim = candidate.learning_path_id && !candidate.plan_id;
  const hasPlan = !!candidate.plan_id;

  return (
    <Shell>
      <div className="bg-white rounded-2xl shadow p-6 mb-6">
        <div className="flex items-center gap-4">
          <div className="w-14 h-14 rounded-full bg-indigo-100 flex items-center justify-center text-2xl font-bold text-indigo-600">
            {user.name[0]?.toUpperCase()}
          </div>
          <div className="flex-1">
            <h1 className="text-xl font-semibold text-gray-800">
              {user.name}
            </h1>
            <p className="text-sm text-gray-500">{user.email}</p>
          </div>
          <div className="text-right">
            <span
              className={`px-3 py-1 rounded-full text-xs font-semibold ${
                CHANNEL_STYLE[candidate.channel || ""]
              }`}
            >
              {candidate.channel || "not started"}
            </span>
          </div>
        </div>

        {candidate.interview_ready && (
          <div className="mt-4 bg-green-50 border border-green-200 rounded-xl p-3 text-sm text-green-800">
            🎉 You've reached the Interview Simulation channel — you're
            interview ready.
          </div>
        )}
      </div>

      {error && (
        <div className="bg-red-50 text-red-600 text-sm px-3 py-2 rounded-lg mb-4">
          {error}
        </div>
      )}

      {needsPath && (
        <Card color="yellow" title="Waiting for path assignment">
          <p className="text-sm text-gray-500">
            Your learning path hasn't been assigned yet. Please check back
            later.
          </p>
        </Card>
      )}

      {needsPrelim && (
        <Card color="yellow" title="Step 1: Preliminary Assessment">
          <p className="text-sm text-gray-500 mb-4">
            A short test to calibrate your starting level and build your
            personalised learning plan.
          </p>
          {preliminaryId ? (
            <Link
              to={`/candidate/test/${preliminaryId}?type=preliminary_test`}
              className="inline-block bg-yellow-400 hover:bg-yellow-500 text-yellow-900 font-semibold px-4 py-2 rounded-lg text-sm transition"
            >
              Start test →
            </Link>
          ) : (
            <button
              onClick={startPreliminary}
              className="bg-yellow-400 hover:bg-yellow-500 text-yellow-900 font-semibold px-4 py-2 rounded-lg text-sm transition"
            >
              Take Assessment →
            </button>
          )}
        </Card>
      )}

      {hasPlan && progress && (
        <>
          {progress.ready_for_advancement && (
            <div className="bg-white rounded-2xl shadow p-6 border-l-4 border-indigo-500 mb-4">
              <div className="flex items-center justify-between flex-wrap gap-3">
                <div>
                  <h2 className="font-semibold text-gray-800 mb-1">
                    🎯 Ready for the advancement test
                  </h2>
                  <p className="text-sm text-gray-500">
                    You've completed every section at the{" "}
                    <span className="font-medium">{candidate.channel}</span>{" "}
                    channel. Take the path-wide test to move to the next level.
                  </p>
                </div>
                <button
                  onClick={startAdvancement}
                  disabled={advancing}
                  className="bg-indigo-500 hover:bg-indigo-600 disabled:bg-gray-300 text-white font-semibold px-5 py-2.5 rounded-lg text-sm transition"
                >
                  {advancing
                    ? "Preparing…"
                    : progress.pending_advancement_assessment_id
                    ? "Resume Test →"
                    : "Take Advancement Test →"}
                </button>
              </div>
            </div>
          )}

          <Card color="indigo" title="Mentor Sessions">
            <p className="text-sm text-gray-500 mb-3">
              Choose a section to practice with your AI mentor.
            </p>
            <div className="space-y-2">
              {progress.sections.map((s) => {
                const done = progress.completed_section_ids.includes(s.id);
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
                    {done ? (
                      <span className="text-green-500 text-sm font-medium">
                        ✓ Done
                      </span>
                    ) : (
                      <Link
                        to={`/candidate/chat/${s.id}`}
                        className="bg-indigo-500 hover:bg-indigo-600 text-white text-sm font-semibold px-4 py-1.5 rounded-lg transition"
                      >
                        {candidate.channel === "simulation"
                          ? "Mock Interview"
                          : "Start Session"}{" "}
                        →
                      </Link>
                    )}
                  </div>
                );
              })}
            </div>
          </Card>

          <Card color="green" title="Progress">
            <p className="text-sm text-gray-500 mb-3">
              See covered concepts, gaps, and your current standing.
            </p>
            <Link
              to="/candidate/progress"
              className="inline-block bg-green-500 hover:bg-green-600 text-white font-semibold px-4 py-2 rounded-lg text-sm transition"
            >
              View Progress →
            </Link>
          </Card>
        </>
      )}
    </Shell>
  );
}

function Card({ color, title, children }) {
  const border = {
    yellow: "border-yellow-400",
    indigo: "border-indigo-400",
    green: "border-green-400",
  }[color];
  return (
    <div
      className={`bg-white rounded-2xl shadow p-6 border-l-4 ${border} mb-4`}
    >
      <h2 className="font-semibold text-gray-800 mb-2">{title}</h2>
      {children}
    </div>
  );
}

function Shell({ children }) {
  return (
    <div className="min-h-screen">
      <Nav
        tabs={[
          { to: "/candidate", label: "Home" },
          { to: "/candidate/progress", label: "Progress" },
        ]}
      />
      <div className="max-w-3xl mx-auto px-4 py-8">{children}</div>
    </div>
  );
}
