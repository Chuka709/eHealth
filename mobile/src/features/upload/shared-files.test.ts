import type { ShareIntentFile } from "expo-share-intent";

import { readShared } from "@/features/upload/shared-files";

const file = (over: Partial<ShareIntentFile>): ShareIntentFile => ({
  fileName: "result.pdf",
  mimeType: "application/pdf",
  path: "content://com.viber.files/123",
  size: 1000,
  width: null,
  height: null,
  duration: null,
  ...over,
});

test("a readable PDF is offered for adding", () => {
  const { picked, notice } = readShared([file({})]);
  expect(picked).toEqual([{ uri: "content://com.viber.files/123", mime: "application/pdf" }]);
  expect(notice).toBeNull();
});

test("an empty list says the shared file could not be read (B9)", () => {
  expect(readShared([])).toEqual({ picked: [], notice: "sharedUnreadable" });
});

test("a file of another kind is refused as unsupported", () => {
  expect(readShared([file({ mimeType: "application/zip" })]).notice).toBe("sharedUnsupported");
});

test("a file without a type is refused, not a crash", () => {
  const untyped = file({ mimeType: null as unknown as string });
  expect(readShared([untyped]).notice).toBe("sharedUnsupported");
});

test("a URI of this app's own provider is refused", () => {
  for (const path of [
    "content://mn.munkhly.labtrack.FileSystemFileProvider/cache/x.pdf",
    "content://mn.munkhly.labtrack.development.FileSystemFileProvider/files/y.pdf",
    "content://0@mn.munkhly.labtrack.FileSystemFileProvider/files/z.pdf", // another user's
    "CONTENT://MN.MUNKHLY.LABTRACK.FileSystemFileProvider/files/z.pdf",
    "content://x@com.viber.files/123", // any userinfo is refused
  ]) {
    expect(readShared([file({ path })]).picked).toEqual([]);
  }
});

test("no share at all gives nothing to add", () => {
  expect(readShared(null).picked).toEqual([]);
});
