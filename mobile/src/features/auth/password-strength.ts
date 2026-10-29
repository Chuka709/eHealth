import { ZxcvbnFactory } from "@zxcvbn-ts/core";
import * as common from "@zxcvbn-ts/language-common";

/** Same lower bound as the server policy (core/security.py); the server has the final word. */
export const MIN_PASSWORD_LENGTH = 10;
export const MAX_PASSWORD_LENGTH = 128;

let factory: ZxcvbnFactory | null = null;

/**
 * 0–4 guessability score for the strength meter only (hint, not a gate): the server's
 * zxcvbn ≥ 3 check decides. The dictionaries load on first use, not at app start.
 */
export function passwordScore(password: string): 0 | 1 | 2 | 3 | 4 {
  if (!password) return 0;
  factory ??= new ZxcvbnFactory({
    graphs: common.adjacencyGraphs,
    dictionary: common.dictionary,
  });
  // zxcvbn is slow on very long input; the server rejects > 128 anyway.
  return factory.check(password.slice(0, MAX_PASSWORD_LENGTH)).score;
}
