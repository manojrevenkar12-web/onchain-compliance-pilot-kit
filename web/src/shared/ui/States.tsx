import styles from "./states.module.css";

export function Skeleton({ lines = 3, label }: { lines?: number; label: string }) {
  return (
    <div className={styles.skeleton} role="status" aria-label={label}>
      {Array.from({ length: lines }, (_, i) => (
        <span key={i} className={styles.bar} style={{ width: `${92 - i * 14}%` }} />
      ))}
    </div>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className={styles.error} role="alert">
      <p>{message}</p>
      {onRetry && (
        <button type="button" className={styles.button} onClick={onRetry}>
          Load again
        </button>
      )}
    </div>
  );
}

export function EmptyState({ title, children }: { title: string; children?: React.ReactNode }) {
  return (
    <div className={styles.empty}>
      <p className={styles.emptyTitle}>{title}</p>
      {children && <p>{children}</p>}
    </div>
  );
}
