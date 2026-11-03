import { configure } from "@testing-library/react-native";

// Router screens render cold in the first test of a file and the suites run in parallel:
// the 1 s default for findBy* made tests flaky under load, not wrong.
configure({ asyncUtilTimeout: 5000 });
