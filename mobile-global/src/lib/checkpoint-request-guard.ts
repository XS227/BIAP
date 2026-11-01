/** Discard out-of-order asynchronous responses after issuer changes or unmount. */
export function createCheckpointRequestGuard() {
  let version = 0;
  return {
    begin: () => ++version,
    invalidate: () => { version += 1; },
    isCurrent: (requestVersion: number) => requestVersion === version,
  };
}
