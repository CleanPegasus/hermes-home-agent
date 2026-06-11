const store = new Map<string, string>();

if (!globalThis.localStorage) {
  Object.defineProperty(globalThis, "localStorage", {
    value: {
      clear: () => store.clear(),
      getItem: (key: string) => store.get(key) ?? null,
      key: (index: number) => Array.from(store.keys())[index] ?? null,
      removeItem: (key: string) => {
        store.delete(key);
      },
      setItem: (key: string, value: string) => {
        store.set(key, value);
      },
      get length() {
        return store.size;
      }
    },
    configurable: true
  });
}
