import type { ReactNode } from "react";
import "./states.css";

export function Loading({ what }: { what: string }) {
  return (
    <div className="state" role="status" aria-live="polite">
      <span className="state-bar" aria-hidden />
      Reading {what} from the warehouse
    </div>
  );
}

export function Failed({ what, message, retry }: { what: string; message: string; retry: () => void }) {
  return (
    <div className="state state-error" role="alert">
      <p>
        Could not read {what}. The API answered: <code>{message.slice(0, 160)}</code>
      </p>
      <p className="muted">Check that the API is running (make api) and the demo data is loaded (make demo).</p>
      <button className="btn" onClick={retry}>Try again</button>
    </div>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="state state-empty">{children}</div>;
}
