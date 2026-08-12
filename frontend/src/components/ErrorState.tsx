import { presentClientError } from "../clientLanguage";

interface ErrorStateProps {
  url: string;
  message: string;
  onRetry: () => void;
}

export function ErrorState({ url, message, onRetry }: ErrorStateProps) {
  return (
    <section className="state error" role="alert">
      <p className="eyebrow eyebrow--danger">Ошибка анализа</p>
      <h1>Не удалось выполнить анализ</h1>
      <p className="status-url">{url}</p>
      <p className="error-message">{presentClientError(message)}</p>
      <p className="hint">
        Если ошибка повторяется, подождите немного и запустите анализ снова. Также проверьте,
        что страница открывается без входа.
      </p>
      <div className="actions">
        <button className="btn btn-primary" type="button" onClick={onRetry}>
          Новый анализ
        </button>
      </div>
    </section>
  );
}
