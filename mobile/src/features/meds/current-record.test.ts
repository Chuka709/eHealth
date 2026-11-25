import { CHECK_TIMEOUT_MS, currentRecord } from "./use-medications";

// the server never answers (a socket left behind by a network change), but honours the abort
const mockGet = jest.fn(
  (_path: string, init: { signal: AbortSignal }) =>
    new Promise((_, reject) => {
      init.signal.addEventListener("abort", () => reject(new Error("aborted")));
    }),
);
jest.mock("@/lib/api", () => ({
  api: { GET: (path: string, init: { signal: AbortSignal }) => mockGet(path, init) },
}));

const P = "00000000-0000-4000-8000-0000000000aa";
const M = "22222222-2222-4222-8222-222222222222";

test("Q24/R8: a check that never answers asks the user - never hanging, never silent", async () => {
  jest.useFakeTimers();
  try {
    const result = currentRecord(P, M, 1_795_573_200_000);
    await jest.advanceTimersByTimeAsync(CHECK_TIMEOUT_MS);
    await expect(result).resolves.toBe("unknown");
  } finally {
    jest.useRealTimers();
  }
});

test("Q24: a network error (offline) still records without asking", async () => {
  mockGet.mockImplementationOnce(async () => {
    throw new TypeError("Network request failed");
  });
  await expect(currentRecord(P, M, 1_795_573_200_000)).resolves.toBeNull();
});
