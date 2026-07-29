import { FormEvent, useEffect, useMemo, useState } from "react";
import { api, subscribeToRun } from "./api";
import type {
  Consultation,
  Profile,
  ProfileDraft,
  Recommendation,
  Run,
  Session,
  TraceEvent,
} from "./types";

const DEFAULT_PROFILE: ProfileDraft = {
  display_name: "Demo người lớn",
  age_group: "adult",
  goals: ["tim mạch"],
  conditions: [],
  medications: [],
  allergies: [],
  pregnancy_status: "not_applicable",
  budget_max_vnd: 500_000,
  preferred_dosage_forms: ["Viên nang mềm"],
};

const SUGGESTIONS = [
  "Tìm sản phẩm Omega-3 phù hợp ngân sách 500.000đ",
  "So sánh hàm lượng Vitamin C của các lựa chọn tốt nhất",
  "Tôi đang dùng thuốc chống đông, cần lưu ý gì?",
];

function splitList(value: string): string[] {
  return value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

function ProfilePanel({
  profiles,
  selected,
  onSelect,
  onSave,
}: {
  profiles: Profile[];
  selected?: Profile;
  onSelect: (profile: Profile) => void;
  onSave: (draft: ProfileDraft, id?: string) => Promise<void>;
}) {
  const [draft, setDraft] = useState<ProfileDraft>(DEFAULT_PROFILE);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (selected) {
      const { id: _id, created_at: _created, updated_at: _updated, ...value } = selected;
      setDraft({
        ...value,
        goals: value.goals ?? [],
        conditions: value.conditions ?? [],
        medications: value.medications ?? [],
        allergies: value.allergies ?? [],
        preferred_dosage_forms: value.preferred_dosage_forms ?? [],
      });
    }
  }, [selected]);

  const field = (name: keyof ProfileDraft, value: unknown) =>
    setDraft((current) => ({ ...current, [name]: value }));

  async function submit(event: FormEvent) {
    event.preventDefault();
    setSaving(true);
    try {
      await onSave(draft, selected?.id);
    } finally {
      setSaving(false);
    }
  }

  return (
    <aside className="panel profile-panel" aria-label="Hồ sơ tư vấn">
      <div className="panel-heading">
        <div>
          <span className="eyebrow">Context</span>
          <h2>Hồ sơ người dùng</h2>
        </div>
        <span className="count">{profiles.length}</span>
      </div>

      {profiles.length > 0 && (
        <div className="profile-switcher">
          {profiles.map((profile) => (
            <button
              className={profile.id === selected?.id ? "profile-chip active" : "profile-chip"}
              key={profile.id}
              onClick={() => onSelect(profile)}
            >
              <span>{profile.display_name.slice(0, 1).toUpperCase()}</span>
              {profile.display_name}
            </button>
          ))}
        </div>
      )}

      <form className="profile-form" onSubmit={submit}>
        <label>
          Tên demo
          <input
            value={draft.display_name}
            onChange={(e) => field("display_name", e.target.value)}
            required
          />
        </label>
        <div className="form-row">
          <label>
            Nhóm tuổi
            <select
              value={draft.age_group}
              onChange={(e) => field("age_group", e.target.value)}
            >
              <option value="child">Trẻ em</option>
              <option value="adolescent">Vị thành niên</option>
              <option value="adult">Người lớn</option>
              <option value="older_adult">Người cao tuổi</option>
            </select>
          </label>
          <label>
            Ngân sách
            <input
              type="number"
              min="1"
              step="10000"
              value={draft.budget_max_vnd}
              onChange={(e) => field("budget_max_vnd", Number(e.target.value))}
            />
          </label>
        </div>
        <label>
          Mục tiêu <small>phân tách bằng dấu phẩy</small>
          <input
            value={draft.goals.join(", ")}
            onChange={(e) => field("goals", splitList(e.target.value))}
            placeholder="tim mạch, xương khớp"
          />
        </label>
        <label>
          Bệnh nền
          <input
            value={draft.conditions.join(", ")}
            onChange={(e) => field("conditions", splitList(e.target.value))}
            placeholder="tăng huyết áp"
          />
        </label>
        <label>
          Thuốc đang dùng
          <input
            value={draft.medications.join(", ")}
            onChange={(e) => field("medications", splitList(e.target.value))}
            placeholder="warfarin"
          />
        </label>
        <label>
          Dị ứng
          <input
            value={draft.allergies.join(", ")}
            onChange={(e) => field("allergies", splitList(e.target.value))}
            placeholder="sữa, hải sản"
          />
        </label>
        <div className="form-row">
          <label>
            Thai / cho con bú
            <select
              value={draft.pregnancy_status}
              onChange={(e) => field("pregnancy_status", e.target.value)}
            >
              <option value="not_applicable">Không áp dụng</option>
              <option value="none">Không</option>
              <option value="pregnant">Đang mang thai</option>
              <option value="breastfeeding">Cho con bú</option>
              <option value="prefer_not_to_say">Không muốn nói</option>
            </select>
          </label>
          <label>
            Dạng ưu tiên
            <input
              value={draft.preferred_dosage_forms.join(", ")}
              onChange={(e) => field("preferred_dosage_forms", splitList(e.target.value))}
              placeholder="Viên nang"
            />
          </label>
        </div>
        <button className="primary-button full" disabled={saving}>
          {saving ? "Đang lưu…" : selected ? "Cập nhật hồ sơ" : "Tạo hồ sơ demo"}
        </button>
      </form>
      <p className="privacy-note">
        <span className="status-dot" /> Lưu cục bộ · không có tài khoản
      </p>
    </aside>
  );
}

function RecommendationCard({ item, rank }: { item: Recommendation; rank: number }) {
  return (
    <article className="recommendation-card">
      <div className="recommendation-rank">0{rank}</div>
      <div className="recommendation-main">
        <div className="recommendation-top">
          <div>
            <h4>{item.name}</h4>
            <p>
              {item.price_vnd.toLocaleString("vi-VN")}đ · {item.dosage_form} · dòng{" "}
              {item.source_row}
            </p>
          </div>
          <div className="score-ring">{Math.round(item.fit_score)}</div>
        </div>
        {item.reasons?.length > 0 && <p className="reason">{item.reasons.join(" · ")}</p>}
        <div className="safety-badge">
          <span /> Safety: {item.safety?.status ?? "đã đánh giá"}
        </div>
      </div>
    </article>
  );
}

function AnswerView({ answer }: { answer: Consultation }) {
  return (
    <div className="answer">
      <p className="answer-label">Nhận định có căn cứ</p>
      <h3>{answer.final_judgment}</h3>
      <div className="recommendations">
        {answer.recommendations.map((item, index) => (
          <RecommendationCard key={item.product_id} item={item} rank={index + 1} />
        ))}
      </div>
      {answer.limitations.length > 0 && (
        <div className="limitations">
          <strong>Giới hạn dữ liệu</strong>
          <ul>
            {answer.limitations.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>
      )}
      <p className="disclaimer">{answer.disclaimer}</p>
    </div>
  );
}

function ChatPanel({
  profile,
  run,
  busy,
  onSend,
  profileRequest,
  onResume,
}: {
  profile?: Profile;
  run?: Run;
  busy: boolean;
  onSend: (message: string) => Promise<void>;
  profileRequest?: TraceEvent;
  onResume: (patch: Partial<ProfileDraft>) => Promise<void>;
}) {
  const [message, setMessage] = useState("");
  const [resumeValues, setResumeValues] = useState<Record<string, string>>({});
  const requestedFields = Array.isArray(profileRequest?.payload.fields)
    ? profileRequest.payload.fields.map(String)
    : ["goals"];

  function resumePatch(): Partial<ProfileDraft> {
    const listFields = new Set([
      "goals",
      "conditions",
      "medications",
      "allergies",
      "preferred_dosage_forms",
    ]);
    return Object.fromEntries(
      requestedFields.map((field) => {
        const value = resumeValues[field] ?? "";
        if (listFields.has(field)) return [field, splitList(value)];
        if (field === "budget_max_vnd") return [field, Number(value)];
        return [field, value];
      }),
    ) as Partial<ProfileDraft>;
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!message.trim()) return;
    const value = message;
    setMessage("");
    await onSend(value);
  }

  return (
    <main className="panel chat-panel" aria-label="Trò chuyện tư vấn">
      <div className="chat-header">
        <div>
          <span className="eyebrow">Grounded consultation</span>
          <h1>Tư vấn thực phẩm chức năng</h1>
          <p>ReAct Agent · OpenAI gpt-4o-mini · Dataset nội bộ</p>
        </div>
        <span className={busy ? "live-badge pulsing" : "live-badge"}>
          <i /> {busy ? "Đang chạy" : "Sẵn sàng"}
        </span>
      </div>

      <section className="conversation">
        {!run && (
          <div className="welcome">
            <div className="brand-mark">Rx</div>
            <span className="eyebrow">Supplement intelligence</span>
            <h2>Hỏi theo nhu cầu.<br />Kiểm tra theo dữ liệu.</h2>
            <p>
              Agent chỉ đưa candidate đã retrieve, chấm điểm và qua safety gate từ
              DataTPCN.csv.
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
        {run && (
          <>
            <div className="message user-message">
              <span>{profile?.display_name.slice(0, 1).toUpperCase() ?? "U"}</span>
              <div>
                <small>Bạn</small>
                <p>{run.query}</p>
              </div>
            </div>
            {busy && (
              <div className="agent-thinking">
                <span className="thinking-mark">A</span>
                <div>
                  <small>ReAct Agent</small>
                  <p><i /><i /><i /> Đang kiểm tra catalog và safety gate</p>
                </div>
              </div>
            )}
            {run.answer && <AnswerView answer={run.answer} />}
            {run.status === "failed" && (
              <div className="error-card">
                Run thất bại: {run.error_code}. Xem trace để biết lỗi cấu hình.
              </div>
            )}
          </>
        )}
        {profileRequest && (
          <form
            className="interrupt-card"
            onSubmit={async (event) => {
              event.preventDefault();
              await onResume(resumePatch());
              setResumeValues({});
            }}
          >
            <span className="eyebrow">Agent đang chờ</span>
            <h3>{String(profileRequest.payload.question ?? "Bổ sung thông tin hồ sơ")}</h3>
            <p>
              Trường cần bổ sung:{" "}
              {Array.isArray(profileRequest.payload.fields)
                ? profileRequest.payload.fields.join(", ")
                : "thông tin an toàn"}
            </p>
            {requestedFields.map((field) => (
              <label key={field}>
                {field}
                <input
                  value={resumeValues[field] ?? ""}
                  onChange={(e) =>
                    setResumeValues((current) => ({
                      ...current,
                      [field]: e.target.value,
                    }))
                  }
                  placeholder={`Nhập ${field}…`}
                  required
                />
              </label>
            ))}
            <button className="primary-button">Bổ sung & tiếp tục run</button>
          </form>
        )}
      </section>

      <form className="composer" onSubmit={submit}>
        <div className="composer-input">
          <textarea
            rows={2}
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            placeholder={profile ? "Hỏi về mục tiêu, thành phần hoặc sản phẩm…" : "Tạo hồ sơ trước khi hỏi…"}
            disabled={!profile || busy}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                event.currentTarget.form?.requestSubmit();
              }
            }}
          />
          <button className="send-button" disabled={!profile || busy || !message.trim()}>
            Gửi <span>↗</span>
          </button>
        </div>
        <p>Thông tin chỉ mang tính tham khảo, không thay thế chẩn đoán y khoa.</p>
      </form>
    </main>
  );
}

function TracePanel({ events, run }: { events: TraceEvent[]; run?: Run }) {
  const [selected, setSelected] = useState<TraceEvent | undefined>();
  const toolCount = events.filter((event) => event.type === "tool.completed").length;
  const tokenCount = events.reduce((total, event) => {
    const usage = event.payload.token_usage as { total_tokens?: number } | undefined;
    return total + (usage?.total_tokens ?? 0);
  }, 0);
  const latency = events.reduce((total, event) => {
    const value = event.payload.latency_ms;
    return total + (typeof value === "number" ? value : 0);
  }, 0);

  useEffect(() => {
    if (events.length > 0) setSelected(events[events.length - 1]);
  }, [events]);

  return (
    <aside className="panel trace-panel" aria-label="ReAct inspector">
      <div className="panel-heading">
        <div>
          <span className="eyebrow">Observability</span>
          <h2>ReAct Inspector</h2>
        </div>
        <span className="trace-status">{run?.status ?? "idle"}</span>
      </div>
      <div className="metrics">
        <div><span>Events</span><strong>{events.length}</strong></div>
        <div><span>Tools</span><strong>{toolCount}/12</strong></div>
        <div><span>Tokens</span><strong>{tokenCount || "—"}</strong></div>
        <div><span>Latency</span><strong>{latency ? `${(latency / 1000).toFixed(1)}s` : "—"}</strong></div>
      </div>
      <div className="trace-list">
        {events.length === 0 ? (
          <div className="empty-trace">
            <div>⌁</div>
            <p>Trace có cấu trúc sẽ xuất hiện khi agent bắt đầu chạy.</p>
            <small>Không hiển thị chain-of-thought.</small>
          </div>
        ) : (
          events.map((event) => (
            <button
              key={`${event.id}-${event.type}`}
              className={selected?.id === event.id ? "trace-event selected" : "trace-event"}
              onClick={() => setSelected(event)}
            >
              <span className={`event-icon ${event.type.split(".")[0]}`} />
              <div>
                <strong>{event.type}</strong>
                <small>#{event.id.toString().padStart(2, "0")}</small>
              </div>
            </button>
          ))
        )}
      </div>
      {selected && (
        <div className="json-view">
          <div><span>Structured payload</span><button onClick={() => navigator.clipboard?.writeText(JSON.stringify(selected.payload, null, 2))}>Copy</button></div>
          <pre>{JSON.stringify(selected.payload, null, 2)}</pre>
        </div>
      )}
      <div className="guardrails">
        <span>GUARDRAILS</span>
        <p><i className="ok" /> 6 vòng tối đa</p>
        <p><i className="ok" /> Safety là gate riêng</p>
        <p><i className="ok" /> Canonical CSV provenance</p>
      </div>
    </aside>
  );
}

export default function App() {
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [session, setSession] = useState<Session>();
  const [run, setRun] = useState<Run>();
  const [events, setEvents] = useState<TraceEvent[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const selected = useMemo(
    () => profiles.find((profile) => profile.id === selectedId),
    [profiles, selectedId],
  );
  const profileRequest = [...events]
    .reverse()
    .find((event) => event.type === "profile.required" && run?.status !== "running");

  useEffect(() => {
    api
      .profiles()
      .then((items) => {
        setProfiles(items);
        if (items[0]) setSelectedId(items[0].id);
      })
      .catch((reason: Error) => setError(reason.message));
  }, []);

  async function saveProfile(draft: ProfileDraft, id?: string) {
    try {
      const saved = id
        ? await api.updateProfile(id, draft)
        : await api.createProfile(draft);
      setProfiles((current) =>
        id ? current.map((item) => (item.id === id ? saved : item)) : [...current, saved],
      );
      setSelectedId(saved.id);
      setSession(undefined);
      setError("");
    } catch (reason) {
      setError((reason as Error).message);
    }
  }

  async function ensureSession(): Promise<Session> {
    if (session && session.profile_id === selectedId) return session;
    const created = await api.createSession(selectedId);
    setSession(created);
    return created;
  }

  function watchRun(runId: string) {
    return subscribeToRun(
      runId,
      (event) => {
        setEvents((current) =>
          current.some((item) => item.id === event.id) ? current : [...current, event],
        );
        if (event.type === "profile.required") {
          setBusy(false);
          api.getRun(runId).then(setRun);
        }
      },
      () => {
        setBusy(false);
        api.getRun(runId).then(setRun);
      },
      () => {
        api.getRun(runId).then((latest) => {
          setRun(latest);
          if (latest.status !== "running" && latest.status !== "queued") setBusy(false);
        });
      },
    );
  }

  async function send(message: string) {
    setBusy(true);
    setEvents([]);
    setError("");
    try {
      const currentSession = await ensureSession();
      const created = await api.createRun(currentSession.id, message);
      setRun(created);
      watchRun(created.id);
    } catch (reason) {
      setBusy(false);
      setError((reason as Error).message);
    }
  }

  async function resume(patch: Partial<ProfileDraft>) {
    if (!run) return;
    setBusy(true);
    try {
      const resumed = await api.resumeRun(run.id, patch, { profile_patch: patch });
      setRun(resumed);
      watchRun(run.id);
    } catch (reason) {
      setBusy(false);
      setError((reason as Error).message);
    }
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <a className="wordmark" href="/">
          <span>Δ</span>
          <div><strong>TPCN Mentor</strong><small>Agent laboratory</small></div>
        </a>
        <div className="dataset-pill"><span /> DataTPCN.csv · 100 sản phẩm</div>
        <div className="version-pill">VERSION 1 <b>OpenAI</b></div>
      </header>
      {error && <div className="global-error">{error}</div>}
      <div className="dashboard">
        <ProfilePanel
          profiles={profiles}
          selected={selected}
          onSelect={(profile) => {
            setSelectedId(profile.id);
            setSession(undefined);
            setRun(undefined);
            setEvents([]);
          }}
          onSave={saveProfile}
        />
        <ChatPanel
          profile={selected}
          run={run}
          busy={busy}
          onSend={send}
          profileRequest={profileRequest}
          onResume={resume}
        />
        <TracePanel events={events} run={run} />
      </div>
    </div>
  );
}
