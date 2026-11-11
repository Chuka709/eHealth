/**
 * Hermes (the phone's JS engine) has no Intl.PluralRules: an ICU plural message ("{n, plural,
 * ...}") failed to format and showed its raw key (found on the emulator, 2.12). Installed only
 * when missing; the app's two languages only. Imported first by the root layout.
 */
import "@formatjs/intl-pluralrules/polyfill.js";
import "@formatjs/intl-pluralrules/locale-data/en.js";
import "@formatjs/intl-pluralrules/locale-data/mn.js";
