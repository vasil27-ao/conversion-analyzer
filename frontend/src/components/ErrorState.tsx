interface ErrorStateProps {
  url: string;
  message: string;
  onRetry: () => void;
}

export function ErrorState({ url, message, onRetry }: ErrorStateProps) {
  return (
    <section className="state error" role="alert">
      <p className="eyebrow eyebrow--danger">
        <span className="eyebrow-index">!!</span>
        Ошибка анализа
      </p>
      <h1>Не удалось выполнить анализ</h1>
      <p className="status-url">{url}</p>
      <p className="error-message">{message}</p>
      <p className="hint">
        Частые причины: страница недоступна, требует авторизации или временно не отвечает.
      </p>
      <div className="actions">
        <button className="btn btn-primary" type="button" onClick={onRetry}>
          Новый анализ
        </button>
      </div>
    </section>
  );
}
