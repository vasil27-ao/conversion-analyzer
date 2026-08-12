import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, createAnalysis, getAnalysis } from "./api";
import { ErrorState } from "./components/ErrorState";
import { ReportPreview } from "./components/ReportPreview";
import { ReportView } from "./components/ReportView";
import { UrlForm } from "./components/UrlForm";
import { WaitingState } from "./components/WaitingState";
import type { AgentResult, AnalysisStatus } from "./types";
import { normalizeUrlInput, validateUrl } from "./urlValidation";

const POLL_INTERVAL_MS = 2000;

type Screen =
  | { kind: "form" }
  | { kind: "waiting"; analysisId: string; url: string; status: AnalysisStatus }
  | { kind: "done"; analysisId: string; url: string; result: AgentResult }
  | { kind: "failed"; url: string; message: string };

export default function App() {
  const [urlInput, setUrlInput] = useState("");
  const [formError, setFormError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [screen, setScreen] = useState<Screen>({ kind: "form" });
  const pollTimerRef = useRef<number | null>(null);

  const clearPoll = useCallback(() => {
    if (pollTimerRef.current !== null) {
      window.clearTimeout(pollTimerRef.current);
      pollTimerRef.current = null;
    }
  }, []);

  const resetToForm = useCallback(() => {
    clearPoll();
    setSubmitting(false);
    setFormError(null);
    setScreen({ kind: "form" });
  }, [clearPoll]);

  useEffect(() => () => clearPoll(), [clearPoll]);

  const waitingId = screen.kind === "waiting" ? screen.analysisId : null;
  const waitingUrl = screen.kind === "waiting" ? screen.url : null;

  useEffect(() => {
    if (!waitingId || !waitingUrl) {
      clearPoll();
      return;
    }

    let cancelled = false;

    const poll = async () => {
      try {
        const payload = await getAnalysis(waitingId);
        if (cancelled) return;

        if (payload.status === "done" && payload.result) {
          setScreen({
            kind: "done",
            analysisId: payload.id,
            url: payload.url,
            result: payload.result,
          });
          return;
        }

        if (payload.status === "failed") {
          setScreen({
            kind: "failed",
            url: payload.url,
            message: payload.error_message || "Анализ завершился с ошибкой.",
          });
          return;
        }

        setScreen({
          kind: "waiting",
          analysisId: payload.id,
          url: payload.url,
          status: payload.status,
        });
        pollTimerRef.current = window.setTimeout(() => {
          void poll();
        }, POLL_INTERVAL_MS);
      } catch (error) {
        if (cancelled) return;
        const message =
          error instanceof ApiError
            ? error.message
            : "Не удалось получить статус анализа. Проверьте интернет и попробуйте ещё раз.";
        setScreen({ kind: "failed", url: waitingUrl, message });
      }
    };

    void poll();

    return () => {
      cancelled = true;
      clearPoll();
    };
  }, [waitingId, waitingUrl, clearPoll]);

  const handleSubmit = async () => {
    const normalized = normalizeUrlInput(urlInput);
    const validationError = validateUrl(normalized);
    if (validationError) {
      setFormError(validationError);
      return;
    }

    setFormError(null);
    setSubmitting(true);

    try {
      const created = await createAnalysis(normalized);
      setScreen({
        kind: "waiting",
        analysisId: created.id,
        url: normalized,
        status: created.status,
      });
    } catch (error) {
      const message =
        error instanceof ApiError
          ? error.message
          : "Не удалось запустить анализ. Проверьте интернет и попробуйте ещё раз.";
      setFormError(message);
    } finally {
      setSubmitting(false);
    }
  };

  const isStart = screen.kind === "form";

  return (
    <div className={`shell ${isStart ? "shell--start" : "shell--work"}`}>
      <header className="masthead">
        <div className="masthead-brand">
          <span className="brand-mark" aria-hidden="true" />
          <span className="brand-name">Conversion Analyzer</span>
        </div>
        <div className="masthead-meta">
          <span className="masthead-tag">CRO · methodology report</span>
          {!isStart ? (
            <button className="btn btn-ghost" type="button" onClick={resetToForm}>
              Новый анализ
            </button>
          ) : null}
        </div>
      </header>

      <main className="stage">
        {screen.kind === "form" ? (
          <section className="start">
            <div className="start-intro">
              <p className="eyebrow">Рабочий инструмент оценки конверсии</p>
              <div className="start-intro-row">
                <h1>
                  Разберите страницу
                  <em> по методике</em>
                </h1>
                <p className="lede">
                  Вставьте URL страницы — получите общую оценку, разбор по 6 блокам, список проблем и
                  план задач для команды.
                </p>
              </div>
              <ul className="start-points">
                <li>Чек-лист из 20 критериев</li>
                <li>Обоснования и рекомендации</li>
                <li>Скачиваемый отчёт</li>
              </ul>
            </div>

            <div className="start-workspace">
              <div className="start-panel">
                <UrlForm
                  value={urlInput}
                  error={formError}
                  submitting={submitting}
                  onChange={(value) => {
                    setUrlInput(value);
                    if (formError) setFormError(null);
                  }}
                  onSubmit={() => {
                    void handleSubmit();
                  }}
                />
              </div>
              <ReportPreview />
            </div>
          </section>
        ) : null}

        {screen.kind === "waiting" ? (
          <WaitingState url={screen.url} status={screen.status} />
        ) : null}

        {screen.kind === "failed" ? (
          <ErrorState url={screen.url} message={screen.message} onRetry={resetToForm} />
        ) : null}

        {screen.kind === "done" ? (
          <ReportView
            analysisId={screen.analysisId}
            url={screen.url}
            result={screen.result}
            onNewAnalysis={resetToForm}
          />
        ) : null}
      </main>
    </div>
  );
}
