import { useCallback, useEffect, useState } from "react";

export type Resource<T> =
  | { state: "loading" }
  | { state: "error"; message: string; retry: () => void }
  | { state: "ready"; data: T; reload: () => void };

export function useResource<T>(load: () => Promise<T>, deps: unknown[] = []): Resource<T> {
  const [res, setRes] = useState<Resource<T>>({ state: "loading" });
  const run = useCallback(() => {
    setRes({ state: "loading" });
    load()
      .then((data) => setRes({ state: "ready", data, reload: run }))
      .catch((e: Error) => setRes({ state: "error", message: e.message, retry: run }));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  useEffect(run, [run]);
  return res;
}
