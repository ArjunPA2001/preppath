import { useEffect, useState } from "react";
import { useParams, useSearchParams, Link, useNavigate } from "react-router-dom";
import Nav from "../../components/Nav.jsx";
import { api } from "../../api.js";

const CHANNEL_INFO = {
  foundation: {
    label: "Foundation Channel",
    desc: "Focus on building core concepts with no time pressure.",
    bg: "bg-blue-50 text-blue-800",
  },
  deepdive: {
    label: "Deep Dive Channel",
    desc: "You're ready to go deeper — trade-offs, edge cases, and design.",
    bg: "bg-purple-50 text-purple-800",
  },
  simulation: {
    label: "Interview Simulation",
    desc: "You're at interview-ready level. Full mock interview format.",
    bg: "bg-green-50 text-green-800",
  },
  improvement: {
    label: "Improvement Mode",
    desc: "Targeted remediation on specific weak areas.",
    bg: "bg-orange-50 text-orange-800",
  },
};

export default function Test() {
  const { assessmentId } = useParams();
  const [search] = useSearchParams();
  const navigate = useNavigate();
  const testType = search.get("type") || "preliminary_test";
  const isAdvancement = testType === "topic_gate";

  const [phase, setPhase] = useState("loading"); // loading | questions | submitting | results
  const [questions, setQuestions] = useState([]);
  const [answers, setAnswers] = useState([]);
  const [idx, setIdx] = useState(0);
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    (async () => {
      try {
        const data = await api.get(`/assessments/${assessmentId}`);
        if (data.status !== "pending") {
          setError("This assessment has already been submitted.");
          return;
        }
        setQuestions(data.questions);
        setAnswers(new Array(data.questions.length).fill(""));
        setPhase("questions");
      } catch (err) {
        setError(err.message);
      }
    })();
  }, [assessmentId]);

  function next() {
    const value = answers[idx] || "";
    const updated = [...answers];
    updated[idx] = value;
    setAnswers(updated);

    if (idx < questions.length - 1) {
      setIdx(idx + 1);
    } else {
      submit(updated);
    }
  }

  async function submit(finalAnswers) {
    setPhase("submitting");
    try {
      const payload = {
        answers: questions.map((q, i) => ({
          question_id: q.question_id,
          answer: finalAnswers[i] || "",
        })),
      };
      const data = await api.post(
        `/assessments/${assessmentId}/submit`,
        payload
      );
      setResult(data.result);
      setPhase("results");
    } catch (err) {
      setError(err.message);
      setPhase("questions");
    }
  }

  if (error) {
    return (
      <Shell>
        <div className="bg-red-50 text-red-700 p-6 rounded-2xl shadow">
          {error}
          <div className="mt-3">
            <Link to="/candidate" className="text-indigo-500 underline text-sm">
              Return home
            </Link>
          </div>
        </div>
      </Shell>
    );
  }

  if (phase === "loading") {
    return (
      <Shell>
        <Spinner label="Preparing your assessment…" />
      </Shell>
    );
  }

  if (phase === "submitting") {
    return (
      <Shell>
        <Spinner
          label="Evaluating your answers…"
          hint="This takes about 10 seconds."
        />
      </Shell>
    );
  }

  if (phase === "results") {
    const info =
      CHANNEL_INFO[result?.channel] || CHANNEL_INFO.foundation;
    const scores = result?.scores || {};
    return (
      <Shell title={isAdvancement ? "Advancement Test" : "Preliminary Assessment"}>
        <div className="bg-white rounded-2xl shadow p-6">
          <h2 className="text-xl font-bold text-gray-800 mb-1">
            Assessment Complete
          </h2>
          <p className="text-sm text-gray-500 mb-4">
            {isAdvancement
              ? "Your new learning channel has been assigned."
              : "Your personalised learning plan is ready."}
          </p>

          <div className={`rounded-xl p-4 mb-4 ${info.bg}`}>
            <p className="text-xs font-semibold uppercase tracking-wide mb-1">
              {isAdvancement ? "New channel" : "Assigned channel"}
            </p>
            <p className="text-2xl font-bold">{info.label}</p>
            <p className="text-sm mt-1">{info.desc}</p>
          </div>

          <div className="grid grid-cols-3 gap-3 mb-4">
            {["accuracy", "depth", "fluency"].map((k) => (
              <div
                key={k}
                className="bg-gray-50 rounded-xl p-3 text-center"
              >
                <p className="text-2xl font-bold text-gray-800">
                  {scores[k] ?? 0}
                </p>
                <p className="text-xs text-gray-500 capitalize">{k}</p>
                <div className="w-full bg-gray-200 rounded-full h-1.5 mt-2">
                  <div
                    className="bg-indigo-400 h-1.5 rounded-full"
                    style={{ width: `${scores[k] ?? 0}%` }}
                  />
                </div>
              </div>
            ))}
          </div>

          {result?.feedback && (
            <div className="bg-gray-50 rounded-xl p-4 mb-4">
              <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">
                Feedback
              </p>
              <p className="text-sm text-gray-700">{result.feedback}</p>
            </div>
          )}

          <div className="grid grid-cols-2 gap-4 mb-6">
            <TagList
              label="Areas to improve"
              items={result?.gaps || []}
              color="red"
            />
            <TagList
              label="Strengths"
              items={result?.strengths || []}
              color="green"
            />
          </div>

          <button
            onClick={() => navigate("/candidate")}
            className="w-full bg-indigo-500 hover:bg-indigo-600 text-white font-semibold py-3 rounded-xl transition"
          >
            Continue to Mentoring →
          </button>
        </div>
      </Shell>
    );
  }

  // questions phase
  const q = questions[idx];
  return (
    <Shell title={isAdvancement ? "Advancement Test" : "Preliminary Assessment"}>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-semibold text-gray-800">
            Question {idx + 1} of {questions.length}
          </h1>
          <p className="text-sm text-gray-400">
            {q.concept_tag?.replace(/_/g, " ")}
          </p>
        </div>
        <div className="w-32 h-2 bg-gray-200 rounded-full overflow-hidden">
          <div
            className="h-full bg-indigo-500 transition-all"
            style={{ width: `${(idx / questions.length) * 100}%` }}
          />
        </div>
      </div>

      <div className="bg-white rounded-2xl shadow p-6 mb-4">
        <p className="text-gray-700 leading-relaxed">{q.text}</p>
      </div>

      <textarea
        rows={6}
        placeholder="Type your answer here…"
        value={answers[idx] || ""}
        onChange={(e) => {
          const updated = [...answers];
          updated[idx] = e.target.value;
          setAnswers(updated);
        }}
        className="w-full border border-gray-200 rounded-xl p-4 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300 resize-none mb-4"
      />

      <button
        onClick={next}
        className="w-full bg-indigo-500 hover:bg-indigo-600 text-white font-semibold py-3 rounded-xl transition"
      >
        {idx === questions.length - 1 ? "Submit Assessment ✓" : "Next Question →"}
      </button>
    </Shell>
  );
}

function Spinner({ label, hint }) {
  return (
    <div className="py-20 text-center">
      <div className="animate-spin w-10 h-10 border-4 border-indigo-500 border-t-transparent rounded-full mx-auto mb-4" />
      <p className="text-gray-700 font-medium mb-1">{label}</p>
      {hint && <p className="text-sm text-gray-400">{hint}</p>}
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

function Shell({ children, title }) {
  return (
    <div className="min-h-screen">
      <Nav
        tabs={[
          { to: "/candidate", label: "Home" },
          { to: "/candidate/progress", label: "Progress" },
        ]}
      />
      <div className="max-w-2xl mx-auto px-4 py-8">
        {title && (
          <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wide mb-2">
            {title}
          </h2>
        )}
        {children}
      </div>
    </div>
  );
}
