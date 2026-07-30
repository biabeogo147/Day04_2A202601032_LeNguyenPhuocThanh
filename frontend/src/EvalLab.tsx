import { useEffect, useMemo, useRef, useState } from "react";
import canonicalCases from "../../version_1/evals/version_1.json";
import { evaluateResult, executeEvalCase, runWorkerPool } from "./eval/runner";
import type { EvalCase, EvalCaseStatus, EvalResult } from "./eval/types";
import "./eval-styles.css";

const CASES = canonicalCases as EvalCase[];
const REPORT_STORAGE_KEY = "tpcn-eval-report-v1";
const CATEGORY_LABELS: Record<string, string> = {
  all: "Tất cả",
  retrieval: "Retrieval",
  context: "Context",
  safety: "Safety",
  grounding: "Grounding",
  injection: "Injection",
};

function safeFailure(evalCase: EvalCase, reason: unknown): EvalResult {
  const message = reason instanceof Error ? reason.message : "Lỗi eval không xác định";
  return {
    caseId: evalCase.id,
    title: evalCase.title,
    category: evalCase.category,
    sessionId: "",
    run: {
      id: "", session_id: "", status: "failed", query: evalCase.turns[0]?.message ?? "",
      answer: null, error_code: "eval_runner_error", created_at: "", updated_at: "",
    },
    events: [], elapsedMs: 0, passed: false, failures: [`runner_error:${message}`],
    actualTools: [], routingPass: false, groundingPass: false,
    safetyApplicable: evalCase.category === "safety", safetyPass: false,
    injectionApplicable: evalCase.category === "injection", injectionPass: false,
    contextPass: false, constraintPass: false, guardrailViolations: [],
    requestedFields: [], interruptCount: 0,
    tokenUsage: { input_tokens: 0, output_tokens: 0, total_tokens: 0 }, latencyMs: 0,
  };
}

function download(name: string, content: string, type: string) {
  const url = URL.createObjectURL(new Blob([content], { type }));
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = name;
  anchor.click();
  URL.revokeObjectURL(url);
}

function restoreResults(): Record<string, EvalResult> {
  try {
    const payload = JSON.parse(localStorage.getItem(REPORT_STORAGE_KEY) ?? "null");
    const items = Array.isArray(payload?.results) ? payload.results as EvalResult[] : [];
    const knownIds = new Set(CASES.map((item) => item.id));
    return Object.fromEntries(
      items.filter((item) => knownIds.has(item.caseId)).map((item) => [item.caseId, item]),
    );
  } catch {
    return {};
  }
}

export default function EvalLab() {
  const restored = useMemo(restoreResults, []);
  const [category, setCategory] = useState("all");
  const [concurrency, setConcurrency] = useState(3);
  const [selectedIds, setSelectedIds] = useState(() => new Set(CASES.map((item) => item.id)));
  const [statuses, setStatuses] = useState<Record<string, EvalCaseStatus>>(() => Object.fromEntries(
    Object.values(restored).map((item) => [item.caseId, item.passed ? "passed" : "failed"]),
  ));
  const [results, setResults] = useState<Record<string, EvalResult>>(restored);
  const [activeCaseId, setActiveCaseId] = useState(Object.keys(restored)[0] ?? CASES[0].id);
  const [running, setRunning] = useState(false);
  const [health, setHealth] = useState<"checking" | "online" | "offline">("checking");
  const stopRef = useRef(false);

  useEffect(() => {
    fetch("/api/v1/health")
      .then((response) => {
        if (!response.ok) throw new Error("offline");
        setHealth("online");
      })
      .catch(() => setHealth("offline"));
  }, []);

  useEffect(() => {
    if (!Object.keys(results).length) return;
    localStorage.setItem(REPORT_STORAGE_KEY, JSON.stringify({
      version: "version_1",
      saved_at: new Date().toISOString(),
      results: Object.values(results),
    }));
  }, [results]);

  const visibleCases = useMemo(
    () => CASES.filter((item) => category === "all" || item.category === category),
    [category],
  );
  const selectedResult = results[activeCaseId];
  const finished = Object.values(statuses).filter((status) => status === "passed" || status === "failed").length;
  const passed = Object.values(statuses).filter((status) => status === "passed").length;
  const failed = Object.values(statuses).filter((status) => status === "failed").length;
  const tokens = Object.values(results).reduce((sum, result) => sum + result.tokenUsage.total_tokens, 0);
  const totalSelected = Object.values(statuses).length || selectedIds.size;

  async function runCases(ids: Set<string>) {
    const selectedCases = CASES.filter((item) => ids.has(item.id));
    if (!selectedCases.length || running) return;
    stopRef.current = false;
    setRunning(true);
    setStatuses((current) => ({
      ...current,
      ...Object.fromEntries(selectedCases.map((item) => [item.id, "queued"])),
    }));
    await runWorkerPool(
      selectedCases,
      concurrency,
      async (evalCase) => {
        setStatuses((current) => ({ ...current, [evalCase.id]: "running" }));
        try {
          return evaluateResult(evalCase, await executeEvalCase(evalCase));
        } catch (error) {
          return safeFailure(evalCase, error);
        }
      },
      {
        shouldStop: () => stopRef.current,
        onResult: (result) => {
          setResults((current) => ({ ...current, [result.caseId]: result }));
          setStatuses((current) => ({
            ...current,
            [result.caseId]: result.passed ? "passed" : "failed",
          }));
          setActiveCaseId(result.caseId);
        },
      },
    );
    setRunning(false);
  }

  function toggleVisible(checked: boolean) {
    setSelectedIds((current) => {
      const next = new Set(current);
      for (const item of visibleCases) checked ? next.add(item.id) : next.delete(item.id);
      return next;
    });
  }

  function exportReport(format: "json" | "csv") {
    const report = {
      version: "version_1",
      created_at: new Date().toISOString(),
      concurrency,
      summary: { total: Object.keys(results).length, passed, failed, total_tokens: tokens },
      results: Object.values(results),
    };
    const stamp = new Date().toISOString().replace(/[:.]/g, "-");
    if (format === "json") {
      download(`eval-${stamp}.json`, JSON.stringify(report, null, 2), "application/json");
      return;
    }
    const rows = [
      ["id", "category", "passed", "failures", "tokens", "latency_ms"],
      ...Object.values(results).map((item) => [
        item.caseId, item.category, String(item.passed), item.failures.join(" | "),
        String(item.tokenUsage.total_tokens), String(item.latencyMs),
      ]),
    ];
    download(`eval-${stamp}.csv`, rows.map((row) => row.map((cell) => `"${cell.replaceAll('"', '""')}"`).join(",")).join("\n"), "text/csv");
  }

  return (
    <div className="eval-shell">
      <header className="eval-topbar">
        <a className="eval-brand" href="/"><span>Δ</span><strong>TPCN Mentor</strong></a>
        <div className="eval-title"><span>VERSION 1</span><h1>Eval Lab</h1></div>
        <div className={`health-pill ${health}`}><i /> Backend {health}</div>
        <a className="back-link" href="/">← Về Chat</a>
      </header>

      <section className="eval-hero">
        <div>
          <span className="eyebrow">Live OpenAI · no automatic retry</span>
          <h2>Đánh giá agent bằng dữ liệu thật,<br />quan sát từng quyết định công khai.</h2>
          <p>30 cases · 5 nhóm rủi ro · mỗi case dùng một session độc lập.</p>
        </div>
        <div className="eval-summary">
          <div><span>Đã xong</span><strong>{finished}<small>/{totalSelected}</small></strong></div>
          <div><span>Pass</span><strong className="pass-text">{passed}</strong></div>
          <div><span>Fail</span><strong className="fail-text">{failed}</strong></div>
          <div><span>Tokens</span><strong>{tokens.toLocaleString("vi-VN")}</strong></div>
        </div>
      </section>

      <section className="eval-controls" aria-label="Điều khiển evaluation">
        <div className="category-tabs">
          {Object.entries(CATEGORY_LABELS).map(([key, label]) => (
            <button key={key} className={category === key ? "active" : ""} onClick={() => setCategory(key)}>
              {label}<small>{key === "all" ? CASES.length : CASES.filter((item) => item.category === key).length}</small>
            </button>
          ))}
        </div>
        <label>Concurrency
          <select aria-label="Concurrency" value={concurrency} disabled={running} onChange={(event) => setConcurrency(Number(event.target.value))}>
            {[1, 2, 3, 4, 5].map((value) => <option key={value} value={value}>{value} workers</option>)}
          </select>
        </label>
        <button className="eval-primary" disabled={running || health === "offline" || selectedIds.size === 0} onClick={() => runCases(selectedIds)}>
          {running ? "Đang chạy…" : `▶ Chạy ${selectedIds.size} case`}
        </button>
        <button disabled={!running} onClick={() => { stopRef.current = true; }}>Dừng xếp hàng</button>
        <button disabled={running || failed === 0} onClick={() => runCases(new Set(Object.values(results).filter((item) => !item.passed).map((item) => item.caseId)))}>Chạy lại fail</button>
      </section>

      <div className="eval-progress"><span style={{ width: totalSelected ? `${(finished / totalSelected) * 100}%` : "0%" }} /></div>

      <main className="eval-workspace">
        <section className="case-panel" aria-label="Eval cases">
          <div className="case-header">
            <label><input type="checkbox" checked={visibleCases.every((item) => selectedIds.has(item.id))} onChange={(event) => toggleVisible(event.target.checked)} /> Chọn nhóm đang xem</label>
            <span>30 cases</span>
          </div>
          <div className="case-list">
            {visibleCases.map((evalCase, index) => {
              const status = statuses[evalCase.id] ?? "idle";
              return (
                <article key={evalCase.id} className={`case-row ${activeCaseId === evalCase.id ? "selected" : ""}`} onClick={() => setActiveCaseId(evalCase.id)}>
                  <input aria-label={`Chọn ${evalCase.title}`} type="checkbox" checked={selectedIds.has(evalCase.id)} onClick={(event) => event.stopPropagation()} onChange={(event) => setSelectedIds((current) => {
                    const next = new Set(current); event.target.checked ? next.add(evalCase.id) : next.delete(evalCase.id); return next;
                  })} />
                  <span className="case-index">{String(CASES.indexOf(evalCase) + 1).padStart(2, "0")}</span>
                  <div><strong>{evalCase.title}</strong><p>{evalCase.tags.join(" · ")}</p></div>
                  <span className={`case-status ${status}`}>{status}</span>
                </article>
              );
            })}
          </div>
        </section>

        <aside className="eval-inspector" aria-label="Eval inspector">
          {selectedResult ? (
            <>
              <div className="inspector-heading">
                <div><span className="eyebrow">{selectedResult.category}</span><h3>{selectedResult.title}</h3></div>
                <span className={`result-badge ${selectedResult.passed ? "passed" : "failed"}`}>{selectedResult.passed ? "PASS" : "FAIL"}</span>
              </div>
              <div className="oracle-grid">
                <div><span>Routing</span><strong>{selectedResult.routingPass ? "✓" : "×"}</strong></div>
                <div><span>Grounding</span><strong>{selectedResult.groundingPass ? "✓" : "×"}</strong></div>
                <div><span>Safety</span><strong>{!selectedResult.safetyApplicable ? "—" : selectedResult.safetyPass ? "✓" : "×"}</strong></div>
                <div><span>Injection</span><strong>{!selectedResult.injectionApplicable ? "—" : selectedResult.injectionPass ? "✓" : "×"}</strong></div>
              </div>
              {selectedResult.failures.length > 0 && <div className="failure-box"><strong>Failure reasons</strong>{selectedResult.failures.map((item) => <code key={item}>{item}</code>)}</div>}
              <div className="run-facts"><span>{selectedResult.events.length} events</span><span>{selectedResult.actualTools.length} tools</span><span>{selectedResult.latencyMs} ms</span><span>{selectedResult.tokenUsage.total_tokens} tokens</span></div>
              <section className="answer-preview"><span>Final answer</span><h4>{selectedResult.run.answer?.final_judgment ?? selectedResult.run.error_code ?? "Không có answer"}</h4></section>
              <details open><summary>Tool route</summary><div className="tool-route">{selectedResult.actualTools.map((tool, index) => <span key={`${tool}-${index}`}>{tool}</span>)}</div></details>
              <details><summary>Structured trace</summary><pre>{JSON.stringify(selectedResult.events, null, 2)}</pre></details>
              <details><summary>Output JSON</summary><pre>{JSON.stringify(selectedResult.run.answer, null, 2)}</pre></details>
            </>
          ) : (
            <div className="inspector-empty"><span>⌁</span><h3>Chưa có kết quả</h3><p>Chạy suite hoặc chọn một case đã hoàn tất để xem oracle, trace và output.</p></div>
          )}
          <div className="export-row">
            <button disabled={!Object.keys(results).length} onClick={() => exportReport("json")}>Export JSON</button>
            <button disabled={!Object.keys(results).length} onClick={() => exportReport("csv")}>Export CSV</button>
          </div>
        </aside>
      </main>
    </div>
  );
}
