// Parsed-frame LRU. A result reset aborts pending requests and invalidates late replies.
export function retainedBytes(value, seen = new Set()) {
  if (value == null || typeof value !== 'object') return typeof value === 'number' ? 8 : 0;
  if (seen.has(value)) return 0;
  seen.add(value);
  if (ArrayBuffer.isView(value)) return value.byteLength;
  return 64 + Object.values(value).reduce((sum, item) => sum + retainedBytes(item, seen), 0);
}

export class FrameCache {
  constructor({maxBytes = 96 * 1024 * 1024, maxFrames = 4} = {}) {
    this.maxBytes = maxBytes;
    this.maxFrames = maxFrames;
    this.entries = new Map();
    this.pending = new Map();
    this.bytes = 0;
    this.epoch = 0;
  }
  clear() {
    this.epoch++;
    for (const item of this.pending.values()) item.controller.abort();
    this.pending.clear();
    this.entries.clear();
    this.bytes = 0;
  }
  cancelExcept(key) {
    for (const [name, item] of this.pending) {
      if (name !== key) {item.controller.abort(); this.pending.delete(name);}
    }
  }
  async get(key, read) {
    if (this.entries.has(key)) {
      const entry = this.entries.get(key);
      this.entries.delete(key);
      this.entries.set(key, entry);
      return {value: entry.value, hit: true};
    }
    if (this.pending.has(key)) return this.pending.get(key).promise;
    const controller = new AbortController(), epoch = this.epoch;
    const promise = (async () => read(controller.signal))().then(value => {
      if (epoch !== this.epoch || controller.signal.aborted) throw new DOMException('Result changed', 'AbortError');
      const bytes = retainedBytes(value);
      if (bytes <= this.maxBytes) {
        while (this.entries.size && (this.entries.size >= this.maxFrames || this.bytes + bytes > this.maxBytes)) {
          const oldest = this.entries.keys().next().value;
          this.bytes -= this.entries.get(oldest).bytes;
          this.entries.delete(oldest);
        }
        this.entries.set(key, {value, bytes});
        this.bytes += bytes;
      }
      return {value, hit: false};
    }).finally(() => {
      if (this.pending.get(key)?.promise === promise) this.pending.delete(key);
    });
    this.pending.set(key, {controller, promise});
    return promise;
  }
}
