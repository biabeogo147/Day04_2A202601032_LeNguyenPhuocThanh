import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { api, subscribeToRun } from "./api";
import type {
  Consultation,
  ConversationContext,
  Recommendation,
  Run,
  Session,
  TraceEvent,
} from "./types";

const SUGGESTIONS = [
  "Tìm sản phẩm Omega-3 phù hợp ngân sách 500.000đ",
  "Blackmores Fish Oil 1000mg có thành phần và liều dùng thế nào?",
  "Tôi đang dùng thuốc chống đông, cần lưu ý gì khi chọn Omega-3?",
];

const FIELD_LABELS: Record<string, string> = {
  age_group: "Nhóm tuổi",
  goals: "Mục tiêu sử dụng",
  conditions: "Bệnh nền",
  medications: "Thuốc đang dùng",
  allergies: "Dị ứng",
  pregnancy_status: "Thai kỳ / cho con bú",
  budget_max_vnd: "Ngân sách tối đa",
  preferred_dosage_forms: "Dạng bào chế ưu tiên",
};

const LIST_FIELDS = new Set([
  "goals",
  "conditions",
  "medications",
  "allergies",
  "preferred_dosage_forms",
]);

export function splitList(value: string): string[] {
  if (
    !value.trim()
    || value === "__none__"
    || value.trim().toLocaleLowerCase("vi") === "không có"
  ) return [];
  return value.split(",").map((item) => item.trim()).filter(Boolean);
}

function RecommendationCard({ item, rank }: { item: Recommendation; rank: number }) {
  return (
    <article className="recommendation-card">
      <span className="recommendation-rank">{String(rank).padStart(2, "0")}</span>
      <div className="recommendation-main">
        <div className="recommendation-top">
          <div>
            <h4>{item.name}</h4>
            <p>
              {item.price_vnd.toLocaleString("vi-VN")}đ · {item.dosage_form} · dòng{" "}
              {item.source_row}
            </p>
          </div>
          <span className="score-ring" title="Điểm phù hợp">
            {Math.round(item.fit_score)}
          </span>
        </div>
        {(item.daily_dosage || item.usage || item.nutrients.length > 0) && (
          <dl className="product-facts">
            {item.daily_dosage && (
              <div><dt>Liều dùng</dt><dd>{item.daily_dosage}</dd></div>
            )}
            {item.usage && (
              <div><dt>Cách dùng</dt><dd>{item.usage}</dd></div>
            )}
            {item.nutrients.length > 0 && (
              <div>
                <dt>Thành phần</dt>
                <dd>
                  {item.nutrients.map((nutrient) => (
                    <span key={`${nutrient.name}-${nutrient.amount}-${nutrient.unit}`}>
                      {nutrient.name} {nutrient.amount.toLocaleString("vi-VN")} {nutrient.unit}
                    </span>
                  ))}
                </dd>
              </div>
            )}
          </dl>
        )}
        {item.reasons?.length > 0 && <p className="reason">{item.reasons.join(" · ")}</p>}
        <span className="safety-badge">
          <i /> {item.safety?.status ?? "đã đánh giá"}
        </span>
      </div>
    </article>
  );
}

export function AnswerView({ answer }: { answer: Consultation }) {
  return (
    <div className="answer agent-message">
      <div className="agent-avatar">A</div>
      <div className="answer-body">
        <small>ReAct Agent</small>
        <h3>{answer.final_judgment}</h3>
        {answer.recommendations.length > 0 && (
          <div className="recommendations">
            {answer.recommendations.map((item, index) => (
              <RecommendationCard key={item.product_id} item={item} rank={index + 1} />
            ))}
          </div>
        )}
        {answer.limitations.length > 0 && (
          <div className="limitations">
            <strong>Giới hạn dữ liệu</strong>
            <ul>
              {answer.limitations.map((item) => <li key={item}>{item}</li>)}
            </ul>
          </div>
        )}
        {answer.follow_up_question && (
          <div className="follow-up-question">
            <strong>Câu hỏi tiếp theo</strong>
            <p>{answer.follow_up_question}</p>
          </div>
        )}
        <p className="disclaimer">{answer.disclaimer}</p>
      </div>
    </div>
  );
}

function ContextStrip({ context }: { context: ConversationContext }) {
  const entries = Object.entries(context);
  if (!entries.length) {
    return (
      <div className="context-strip empty">
        <span>Ngữ cảnh phiên</span>
        <p>Agent sẽ chỉ hỏi thêm khi câu hỏi cần thông tin cá nhân.</p>
      </div>
    );
  }
  return (
    <div className="context-strip">
      <span>Đã ghi nhận</span>
      <div>
        {entries.map(([key, value]) => {
          const shown = Array.isArray(value)
            ? value.length ? value.join(", ") : "Không có"
            : key === "budget_max_vnd" && typeof value === "number"
              ? `${value.toLocaleString("vi-VN")}đ`
              : String(value);
          return <span className="context-chip" key={key}>{FIELD_LABELS[key] ?? key}: {shown}</span>;
        })}
      </div>
    </div>
  );
}

function ContextRequest({
  event,
  busy,
  onResume,
}: {
  event: TraceEvent;
  busy: boolean;
  onResume: (patch: ConversationContext) => Promise<void>;
}) {
  const fields = Array.isArray(event.payload.fields)
    ? event.payload.fields.map(String)
    : ["goals"];
  const [values, setValues] = useState<Record<string, string>>({});

  function buildPatch(): ConversationContext | null {
    const patch: Record<string, unknown> = {};
    for (const field of fields) {
      const value = values[field];
      if (value === undefined || value === "") return null;
      if (LIST_FIELDS.has(field)) patch[field] = splitList(value);
      else if (field === "budget_max_vnd") patch[field] = Number(value);
      else patch[field] = value;
    }
    return patch as ConversationContext;
  }

  return (
    <form
      className="interrupt-card"
      onSubmit={async (eventObject) => {
        eventObject.preventDefault();
        const patch = buildPatch();
        if (patch) await onResume(patch);
      }}
    >
      <div className="interrupt-heading">
        <span className="agent-avatar">A</span>
        <div>
          <small>Agent cần thêm ngữ cảnh</small>
          <h3>{String(event.payload.question ?? "Bạn bổ sung giúp mình vài thông tin nhé.")}</h3>
        </div>
      </div>
      <p className="context-explain">
        Chỉ dùng trong cuộc trò chuyện này. Bạn có thể chọn “Không có” cho các mục phù hợp.
      </p>
      <div className="context-form-grid">
        {fields.map((field) => (
          <label key={field}>
            <span>{FIELD_LABELS[field] ?? field}</span>
            {field === "age_group" ? (
              <select
                aria-label={FIELD_LABELS[field]}
                value={values[field] ?? ""}
                onChange={(e) => setValues((current) => ({ ...current, [field]: e.target.value }))}
              >
                <option value="">Chọn nhóm tuổi…</option>
                <option value="child">Trẻ em</option>
                <option value="adolescent">Vị thành niên</option>
                <option value="adult">Người lớn</option>
                <option value="older_adult">Người cao tuổi</option>
              </select>
            ) : field === "pregnancy_status" ? (
              <select
                aria-label={FIELD_LABELS[field]}
                value={values[field] ?? ""}
                onChange={(e) => setValues((current) => ({ ...current, [field]: e.target.value }))}
              >
                <option value="">Chọn trạng thái…</option>
                <option value="not_applicable">Không áp dụng</option>
                <option value="none">Không mang thai / cho con bú</option>
                <option value="pregnant">Đang mang thai</option>
                <option value="breastfeeding">Đang cho con bú</option>
                <option value="prefer_not_to_say">Không muốn chia sẻ</option>
              </select>
            ) : (
              <div className="context-input-row">
                <input
                  aria-label={FIELD_LABELS[field] ?? field}
                  type={field === "budget_max_vnd" ? "number" : "text"}
                  min={field === "budget_max_vnd" ? 0 : undefined}
                  step={field === "budget_max_vnd" ? 10000 : undefined}
                  value={values[field] === "__none__" ? "" : values[field] ?? ""}
                  disabled={values[field] === "__none__"}
                  onChange={(e) => setValues((current) => ({ ...current, [field]: e.target.value }))}
                  placeholder={field === "budget_max_vnd" ? "Ví dụ: 500000" : "Phân tách bằng dấu phẩy"}
                />
                {LIST_FIELDS.has(field) && (
                  <button
                    type="button"
                    className={values[field] === "__none__" ? "none-button active" : "none-button"}
                    onClick={() => setValues((current) => ({
                      ...current,
                      [field]: current[field] === "__none__" ? "" : "__none__",
                    }))}
                  >
                    Không có
                  </button>
                )}
              </div>
            )}
          </label>
        ))}
      </div>
      <button className="primary-button" disabled={busy || buildPatch() === null}>
        {busy ? "Đang tiếp tục…" : "Tiếp tục tư vấn"}
      </button>
    </form>
  );
}

function ChatPanel({
  runs,
  context,
  busy,
  profileRequest,
  onSend,
  onResume,
}: {
  runs: Run[];
  context: ConversationContext;
  busy: boolean;
  profileRequest?: TraceEvent;
  onSend: (message: string) => Promise<void>;
  onResume: (patch: ConversationContext) => Promise<void>;
}) {
  const [message, setMessage] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView?.({ behavior: "smooth" });
  }, [runs, profileRequest, busy]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    const value = message.trim();
    if (!value) return;
    setMessage("");
    await onSend(value);
  }

  return (
    <main className="panel chat-panel" aria-label="Trò chuyện tư vấn">
      <div className="chat-header">
        <div>
          <span className="eyebrow">Grounded consultation</span>
          <h1>Tư vấn thực phẩm chức năng</h1>
          <p>ReAct Agent · gpt-4o-mini · 100 sản phẩm trong DataTPCN.csv</p>
        </div>
        <span className={busy ? "live-badge pulsing" : "live-badge"}>
          <i /> {busy ? "Đang phân tích" : "Sẵn sàng"}
        </span>
      </div>
      <ContextStrip context={context} />

      <section className="conversation">
        {runs.length === 0 && (
          <div className="welcome">
            <div className="brand-mark">Rx</div>
            <span className="eyebrow">Bắt đầu ngay, không cần tạo hồ sơ</span>
            <h2>Bạn đang muốn tìm hiểu<br />sản phẩm nào?</h2>
            <p>
              Hỏi theo tên, thành phần hoặc nhu cầu. Nếu cần tư vấn cá nhân,
              agent sẽ hỏi thêm đúng thông tin liên quan ngay trong cuộc trò chuyện.
            </p>
            <div className="suggestions">
              {SUGGESTIONS.map((suggestion) => (
                <button key={suggestion} onClick={() => setMessage(suggestion)}>
                  <span>↗</span> {suggestion}
                </button>
              ))}
            </div>
          </div>
        )}

        {runs.map((run) => (
          <div className="turn" key={run.id}>
            <div className="message user-message">
              <span>U</span>
              <div><small>Bạn</small><p>{run.query}</p></div>
            </div>
            {run.answer && <AnswerView answer={run.answer} />}
            {run.status === "failed" && (
              <div className="error-card">
                Không thể hoàn tất câu trả lời ({run.error_code ?? "unknown_error"}).
                Hãy kiểm tra kết nối backend và cấu hình API key.
              </div>
            )}
          </div>
        ))}

        {busy && !profileRequest && (
          <div className="agent-thinking">
            <span className="agent-avatar">A</span>
            <div>
              <small>ReAct Agent</small>
              <p><i /><i /><i /> Đang truy xuất catalog và kiểm tra căn cứ</p>
            </div>
          </div>
        )}
        {profileRequest && (
          <ContextRequest event={profileRequest} busy={busy} onResume={onResume} />
        )}
        <div ref={bottomRef} />
      </section>

      <form className="composer" onSubmit={submit}>
        <div className="composer-input">
          <textarea
            aria-label="Câu hỏi tư vấn"
            rows={2}
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            placeholder="Hỏi về mục tiêu, thành phần hoặc sản phẩm…"
            disabled={busy || Boolean(profileRequest)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                event.currentTarget.form?.requestSubmit();
              }
            }}
          />
          <button className="send-button" disabled={busy || Boolean(profileRequest) || !message.trim()}>
            Gửi <span>↗</span>
          </button>
        </div>
        <p>TPCN không phải thuốc và không thay thế thuốc chữa bệnh.</p>
      </form>
    </main>
  );
}

function TracePanel({ events, run }: { events: TraceEvent[]; run?: Run }) {
  const [selected, setSelected] = useState<TraceEvent>();
  const toolCount = events.filter((event) => event.type === "tool.completed").length;
  const latency = events.reduce((total, event) => {
    const value = event.payload.latency_ms;
    return total + (typeof value === "number" ? value : 0);
  }, 0);

  useEffect(() => {
    setSelected(events.at(-1));
  }, [events]);

  return (
    <aside className="panel trace-panel" aria-label="ReAct inspector">
      <div className="panel-heading">
        <div><span className="eyebrow">Observability</span><h2>ReAct Inspector</h2></div>
        <span className="trace-status">{run?.status ?? "idle"}</span>
      </div>
      <div className="metrics">
        <div><span>Events</span><strong>{events.length}</strong></div>
        <div><span>Tools</span><strong>{toolCount}/12</strong></div>
        <div><span>Latency</span><strong>{latency ? `${(latency / 1000).toFixed(1)}s` : "—"}</strong></div>
      </div>
      <div className="trace-list">
        {events.length === 0 ? (
          <div className="empty-trace">
            <div>⌁</div>
            <p>Decision, retrieval, ranking và safety sẽ xuất hiện tại đây.</p>
            <small>Không hiển thị chain-of-thought.</small>
          </div>
        ) : events.map((event) => (
          <button
            key={`${event.id}-${event.type}`}
            className={selected?.id === event.id ? "trace-event selected" : "trace-event"}
            onClick={() => setSelected(event)}
          >
            <i className={`event-icon ${event.type.split(".")[0]}`} />
            <span><strong>{event.type}</strong><small>#{String(event.id).padStart(2, "0")}</small></span>
          </button>
        ))}
      </div>
      {selected && (
        <div className="json-view">
          <div>
            <span>Structured payload</span>
            <button onClick={() => navigator.clipboard?.writeText(JSON.stringify(selected.payload, null, 2))}>
              Copy
            </button>
          </div>
          <pre>{JSON.stringify(selected.payload, null, 2)}</pre>
        </div>
      )}
      <div className="guardrails">
        <span>GUARDRAILS</span>
        <p><i /> Safety gate độc lập</p>
        <p><i /> Canonical CSV provenance</p>
        <p><i /> Không lưu chain-of-thought</p>
      </div>
    </aside>
  );
}

export default function App() {
  const [session, setSession] = useState<Session>();
  const [runs, setRuns] = useState<Run[]>([]);
  const [eventsByRun, setEventsByRun] = useState<Record<string, TraceEvent[]>>({});
  const [currentRunId, setCurrentRunId] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const currentRun = useMemo(
    () => runs.find((run) => run.id === currentRunId),
    [runs, currentRunId],
  );
  const currentEvents = eventsByRun[currentRunId] ?? [];
  const profileRequest = [...currentEvents].reverse().find(
    (event) => event.type === "profile.required" && currentRun?.status === "interrupted",
  );

  function replaceRun(run: Run) {
    setRuns((current) => current.some((item) => item.id === run.id)
      ? current.map((item) => item.id === run.id ? run : item)
      : [...current, run]);
  }

  function watchRun(runId: string, lastEventId = 0) {
    return subscribeToRun(
      runId,
      (event) => {
        setEventsByRun((current) => {
          const events = current[runId] ?? [];
          return events.some((item) => item.id === event.id)
            ? current
            : { ...current, [runId]: [...events, event] };
        });
      },
      () => {
        api.getRun(runId).then((latest) => {
          replaceRun(latest);
          setBusy(false);
        }).catch((reason: Error) => {
          setBusy(false);
          setError(reason.message);
        });
      },
      () => {
        api.getRun(runId).then((latest) => {
          replaceRun(latest);
          if (!["running", "queued"].includes(latest.status)) setBusy(false);
        }).catch(() => setBusy(false));
      },
      lastEventId,
    );
  }

  async function ensureSession(): Promise<Session> {
    if (session) return session;
    const created = await api.createSession();
    setSession(created);
    return created;
  }

  async function send(message: string) {
    setBusy(true);
    setError("");
    try {
      const currentSession = await ensureSession();
      const created = await api.createRun(currentSession.id, message);
      replaceRun(created);
      setCurrentRunId(created.id);
      setEventsByRun((current) => ({ ...current, [created.id]: [] }));
      watchRun(created.id);
    } catch (reason) {
      setBusy(false);
      setError((reason as Error).message);
    }
  }

  async function resume(patch: ConversationContext) {
    if (!currentRun || !session) return;
    setBusy(true);
    setError("");
    try {
      const resumed = await api.resumeRun(
        currentRun.id,
        patch,
        { context_patch: patch },
      );
      replaceRun(resumed);
      setSession((current) => current ? { ...current, context: { ...current.context, ...patch } } : current);
      const lastEventId = currentEvents.reduce(
        (maximum, event) => Math.max(maximum, event.id),
        0,
      );
      watchRun(currentRun.id, lastEventId);
    } catch (reason) {
      setBusy(false);
      setError((reason as Error).message);
    }
  }

  function resetConversation() {
    if (busy) return;
    setSession(undefined);
    setRuns([]);
    setEventsByRun({});
    setCurrentRunId("");
    setError("");
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="wordmark">
          <span>Δ</span>
          <div><strong>TPCN Mentor</strong><small>Agent laboratory</small></div>
        </div>
        <div className="dataset-pill"><i /> DataTPCN.csv · 100 sản phẩm</div>
        <a className="eval-nav-button" href="/eval" aria-label="Mở Eval Lab">
          Eval Lab <span>↗</span>
        </a>
        <button className="new-chat-button" onClick={resetConversation} disabled={busy}>
          <span>＋</span> Cuộc trò chuyện mới
        </button>
        <div className="version-pill">VERSION 1 <b>OpenAI</b></div>
      </header>
      {error && <div className="global-error">{error}</div>}
      <div className="dashboard">
        <ChatPanel
          runs={runs}
          context={session?.context ?? {}}
          busy={busy}
          profileRequest={profileRequest}
          onSend={send}
          onResume={resume}
        />
        <TracePanel events={currentEvents} run={currentRun} />
      </div>
    </div>
  );
}
