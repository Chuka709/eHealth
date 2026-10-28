import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

type Tree = { [key: string]: string | Tree };

const load = (lang: string): Tree =>
  JSON.parse(readFileSync(new URL(`../messages/${lang}.json`, import.meta.url), "utf8")) as Tree;

function keys(tree: Tree, prefix = ""): string[] {
  return Object.entries(tree).flatMap(([k, v]) =>
    typeof v === "string" ? [`${prefix}${k}`] : keys(v, `${prefix}${k}.`),
  );
}

test("mn and en define exactly the same message keys", () => {
  assert.deepEqual(keys(load("mn")).sort(), keys(load("en")).sort());
});

test("no message is empty", () => {
  for (const lang of ["mn", "en"]) {
    const tree = load(lang);
    for (const key of keys(tree)) {
      const value = key.split(".").reduce<string | Tree>((node, part) => (node as Tree)[part] as string | Tree, tree);
      assert.ok(typeof value === "string" && value.trim().length > 0, `${lang}:${key}`);
    }
  }
});
