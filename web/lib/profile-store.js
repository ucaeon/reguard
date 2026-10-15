import { requestJson } from "./api-client.js";

// Shared only in memory; no account data is persisted in browser storage.
export function createProfileStore(
  load = () => requestJson("/api/v1/me/profile"),
) {
  let state = { profile: null, loading: true, error: null };
  let pending = null;
  let revision = 0;
  const listeners = new Set();
  const emit = (next) => {
    state = next;
    listeners.forEach((fn) => fn());
  };
  return {
    getSnapshot: () => state,
    subscribe: (fn) => {
      listeners.add(fn);
      return () => listeners.delete(fn);
    },
    refresh() {
      if (pending) return pending;
      const version = revision;
      pending = Promise.resolve()
        .then(load)
        .then(
          (profile) => {
            if (version === revision)
              emit({ profile, loading: false, error: null });
          },
          (error) => {
            if (version === revision)
              emit({
                profile: error.status === 401 ? null : state.profile,
                loading: false,
                error: error.status === 401 ? null : error,
              });
          },
        )
        .finally(() => {
          pending = null;
        });
      return pending;
    },
    update(profile) {
      revision++;
      emit({ profile, loading: false, error: null });
    },
  };
}
export const profileStore = createProfileStore();
