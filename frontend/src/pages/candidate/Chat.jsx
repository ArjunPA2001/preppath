import { useEffect, useRef, useState } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import { api } from "../../api.js";
import { getUser } from "../../auth.js";

const CHANNEL_STYLE = {
  foundation: "bg-blue-100 text-blue-700",
  deepdive: "bg-purple-100 text-purple-700",
  simulation: "bg-green-100 text-green-700",
  improvement: "bg-orange-100 text-orange-700",
};

export default function Chat() {
  const { sectionId } = useParams();
  const navigate = useNavigate();
  const user = getUser();
  const candidateId = user?.candidate?.id;

  const [sessionId, setSessionId] = useState(null);
  const [channel, setChannel] = useState("");
  const [sectionName, setSectionName] = useState("");
  const [currentQ, setCurrentQ] = useState(null);
  const [requiredConcepts, setRequiredConcepts] = useState([]);
  const [coveredConcepts, setCoveredConcepts] = useState([]);
  const [answerCount, setAnswerCount] = useState(0);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [gateFired, setGateFired] = useState(false);
  const [allSectionsCompleted, setAllSectionsCompleted] = useState(false);
  const [error, setError] = useState("");
  const endRef = useRef(null);

  useEffect(() => {
    (async () => {
      if (!candidateId) {
        setError("Missing candidate profile.");
        return;
      }
      try {
        const data = await api.post("/sessions", {
          candidate_id: candidateId,
          section_id: parseInt(sectionId),
        });
        setSessionId(data.session_id);
        setChannel(data.channel);
        setSectionName(data.section?.name || "");
        setRequiredConcepts(data.required_concepts || []);
        if (data.first_question) setCurrentQ(data.first_question);
        if (data.opening_message) {
          setMessages([{ role: "mentor", text: data.opening_message }]);
        }
      } catch (err) {
        setError(err.message);
      }
    })();
  }, [candidateId, sectionId]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, busy]);

  async function send() {
    const text = input.trim();
    if (!text || busy || !sessionId) return;
    setInput("");
    setBusy(true);
    setMessages((m) => [...m, { role: "user", text }]);

    try {
      const res = await fetch(`/sessions/${sessionId}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ candidate_id: candidateId, message: text }),
      });
      const raw = await res.text();

      const metaMatch = raw.match(/\[META\]([\s\S]*?)\[\/META\]/);
      let meta = null;
      if (metaMatch) {
        try {
          meta = JSON.parse(metaMatch[1]);
        } catch {}
      }
      const clean = raw
        .replace(/\[META\][\s\S]*?\[\/META\]/, "")
        .replace(/\[ERROR\][\s\S]*?\[\/ERROR\]/, "")
        .trim();

      if (clean) {
        setMessages((m) => [...m, { role: "mentor", text: clean }]);
      }

      if (meta) {
        setAnswerCount(meta.answer_count ?? 0);
        if (meta.covered_concepts) setCoveredConcepts(meta.covered_concepts);
        if (meta.next_question) setCurrentQ(meta.next_question);
        if (meta.gate_fired) {
          setGateFired(true);
          setAllSectionsCompleted(!!meta.all_sections_completed);
        }
      }
    } catch (err) {
      setMessages((m) => [
        ...m,
        { role: "mentor", text: "Connection error. Please try again." },
      ]);
    } finally {
      setBusy(false);
    }
  }

  async function endSession() {
    if (!sessionId) return;
    if (!confirm("End this session?")) return;
    await api.post(`/sessions/${sessionId}/end`, {
      candidate_id: candidateId,
    });
    navigate("/candidate/progress");
  }

  return (
    <div className="h-screen flex flex-col bg-gray-50">
      <nav className="bg-white border-b border-gray-200 px-4 py-3 flex items-center justify-between flex-shrink-0">
        <div className="flex items-center gap-3">
          <Link
            to="/candidate"
            className="text-gray-400 hover:text-gray-600 text-sm"
          >
            ← Home
          </Link>
          <div>
            <span className="font-semibold text-gray-800">
              {sectionName || "Mentor Session"}
            </span>
            {channel && (
              <span
                className={`ml-2 px-2 py-0.5 rounded-full text-xs font-semibold ${
                  CHANNEL_STYLE[channel] || "bg-gray-100 text-gray-500"
                }`}
              >
                {channel}
              </span>
            )}
          </div>
        </div>
        <button
          onClick={endSession}
          className="text-sm text-red-500 hover:text-red-700 border border-red-200 hover:border-red-400 px-3 py-1.5 rounded-lg transition"
        >
          End Session
        </button>
      </nav>

      {currentQ && (
        <div className="bg-indigo-50 border-b border-indigo-100 px-4 py-3 flex-shrink-0">
          <div className="max-w-3xl mx-auto">
            <p className="text-xs font-semibold text-indigo-400 uppercase tracking-wide mb-1">
              Current concept:{" "}
              <span className="normal-case">
                {currentQ.concept_tag?.replace(/_/g, " ")}
              </span>
            </p>
            <p className="text-sm text-indigo-800 leading-snug">
              {currentQ.text}
            </p>
          </div>
        </div>
      )}

      <div className="bg-white border-b border-gray-100 px-4 py-2 flex-shrink-0">
        <div className="max-w-3xl mx-auto flex items-center gap-3">
          <span className="text-xs text-gray-400 whitespace-nowrap">
            Section progress
          </span>
          <div className="flex-1 flex gap-1.5 flex-wrap">
            {requiredConcepts.map((c) => {
              const covered = coveredConcepts.includes(c);
              return (
                <span
                  key={c}
                  className={`text-xs px-2 py-0.5 rounded-full transition ${
                    covered
                      ? "bg-green-100 text-green-700"
                      : "bg-gray-100 text-gray-400"
                  }`}
                >
                  {c.replace(/_/g, " ")}
                </span>
              );
            })}
          </div>
          <span className="text-xs text-gray-400">
            {answerCount} answered
          </span>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto px-4 py-4">
        <div className="max-w-3xl mx-auto space-y-3">
          {error && (
            <div className="bg-red-50 text-red-700 px-3 py-2 rounded-lg text-sm">
              {error}
            </div>
          )}
          {messages.map((m, i) => (
            <Bubble key={i} role={m.role} text={m.text} />
          ))}
          {busy && <Typing />}
          {gateFired && (
            <div className="flex flex-col items-center gap-3 py-4">
              <div className="bg-green-50 border border-green-200 rounded-xl px-4 py-3 text-sm text-green-800 text-center max-w-md">
                ✓ Section complete!{" "}
                {allSectionsCompleted
                  ? "Every section at this channel is done — head back home to take the advancement test."
                  : "Head back home and pick the next section to continue."}
              </div>
              <button
                onClick={() => navigate("/candidate")}
                className="bg-indigo-500 hover:bg-indigo-600 text-white font-semibold px-8 py-3 rounded-xl shadow transition text-sm"
              >
                Back to Home →
              </button>
            </div>
          )}
          <div ref={endRef} />
        </div>
      </div>

      <div className="bg-white border-t border-gray-200 px-4 py-3 flex-shrink-0">
        <div className="max-w-3xl mx-auto flex gap-2">
          <textarea
            rows={2}
            value={input}
            disabled={gateFired || busy}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                send();
              }
            }}
            placeholder={
              gateFired ? "Session complete." : "Type your answer or question…"
            }
            className="flex-1 border border-gray-200 rounded-xl px-4 py-2 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-indigo-300 disabled:bg-gray-100"
          />
          <button
            onClick={send}
            disabled={busy || gateFired}
            className="bg-indigo-500 hover:bg-indigo-600 disabled:bg-gray-200 text-white font-semibold px-5 rounded-xl transition"
          >
            Send
          </button>
        </div>
      </div>
    </div>
  );
}

function Bubble({ role, text }) {
  const mine = role === "user";
  return (
    <div className={`flex ${mine ? "justify-end" : "justify-start"}`}>
      <div
        className={`max-w-[80%] px-4 py-3 text-sm leading-relaxed whitespace-pre-wrap ${
          mine
            ? "bg-indigo-500 text-white rounded-[1.25rem_1.25rem_0.25rem_1.25rem]"
            : "bg-white text-gray-800 shadow rounded-[1.25rem_1.25rem_1.25rem_0.25rem]"
        }`}
      >
        {text}
      </div>
    </div>
  );
}

function Typing() {
  return (
    <div className="flex justify-start">
      <div className="bg-white shadow rounded-[1.25rem_1.25rem_1.25rem_0.25rem] px-4 py-3 flex gap-1 items-center">
        <span className="w-2 h-2 rounded-full bg-gray-400 animate-pulse" />
        <span
          className="w-2 h-2 rounded-full bg-gray-400 animate-pulse"
          style={{ animationDelay: "0.2s" }}
        />
        <span
          className="w-2 h-2 rounded-full bg-gray-400 animate-pulse"
          style={{ animationDelay: "0.4s" }}
        />
      </div>
    </div>
  );
}
