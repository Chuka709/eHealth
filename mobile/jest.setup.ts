import { configure } from "@testing-library/react-native";

// Router screens render cold in the first test of a file and the suites run in parallel:
// the 1 s default for findBy* made tests flaky under load, not wrong.
configure({ asyncUtilTimeout: 5000 });
// The whole-flow tests (consents onboarding, language switch) await several screens in a row; with
// the per-test limit at Jest's 5 s default, one slow findBy used it all up (1.12: the flakiness).
jest.setTimeout(20_000);
