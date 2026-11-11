/** One board's short-lived reads, never shared across workspaces or sessions. */
export class BoardReadCache {
  private values = new Map<string, { value: unknown; until: number }>();
  private pending = new Map<string, { key: string; controller: AbortController; promise: Promise<unknown> }>();

  constructor(private now = Date.now, private ttl = 30_000) {}

  read<T>(lane: string, key: string, load: (signal: AbortSignal) => Promise<T>, fresh = false): Promise<T> {
    const active = this.pending.get(lane);
    if (!fresh && active?.key === key) return active.promise as Promise<T>;
    active?.controller.abort();
    this.pending.delete(lane);
    const cached = this.values.get(key);
    if (!fresh && cached && cached.until > this.now()) return Promise.resolve(cached.value as T);
    this.values.delete(key);
    const controller = new AbortController();
    const promise = load(controller.signal).then((value) => {
      if (!controller.signal.aborted) {
        this.values.set(key, { value, until: this.now() + this.ttl });
        if (this.values.size > 24) this.values.delete(this.values.keys().next().value!);
      }
      return value;
    }).finally(() => {
      if (this.pending.get(lane)?.controller === controller) this.pending.delete(lane);
    });
    this.pending.set(lane, { key, controller, promise });
    return promise;
  }

  clear() {
    this.values.clear();
    for (const { controller } of this.pending.values()) controller.abort();
    this.pending.clear();
  }
}
