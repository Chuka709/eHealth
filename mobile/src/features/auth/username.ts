import { z } from "zod";

/** Same rule as the API (`^[a-z0-9._]{3,32}$`, lower-cased); messages are app.common keys. */
export const usernameSchema = z
  .string()
  .trim()
  .toLowerCase()
  .min(1, "fieldRequired")
  .regex(/^[a-z0-9._]{3,32}$/, "usernameFormat");
