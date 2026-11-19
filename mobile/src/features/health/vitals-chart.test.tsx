import mn from "@labtrack/shared/messages/mn.json";
import { fireEvent, render, screen } from "@testing-library/react-native";
import * as echarts from "echarts/core";
import { IntlProvider } from "use-intl";

import type { Vital } from "./use-health";
import { VitalsChart } from "./vitals-chart";

type Recorded = { option: { series: { name: string; data: unknown[] }[] } };
const charts = (echarts as unknown as { __charts: Recorded[] }).__charts;

const v = (kind: string, value: string, at: string, group: string | null = null): Vital =>
  ({
    id: `${kind}-${at}`,
    kind,
    value,
    unit: kind === "weight" ? "kg" : "mmHg",
    measured_at: at,
    group_id: group,
  }) as unknown as Vital;

test("blood pressure is one chart of its two numbers, as entered; a single reading has none", async () => {
  const vitals = [
    v("bp_systolic", "120", "2026-10-01T08:00:00Z", "g1"),
    v("bp_diastolic", "80", "2026-10-01T08:00:00Z", "g1"),
    v("bp_systolic", "135", "2026-10-08T08:00:00Z", "g2"),
    v("bp_diastolic", "85", "2026-10-08T08:00:00Z", "g2"),
    v("weight", "70", "2026-10-01T08:00:00Z"),
  ];
  await render(
    <IntlProvider locale="mn" messages={mn}>
      <VitalsChart vitals={vitals} />
    </IntlProvider>,
  );
  const box = screen.getByLabelText(/график, 4 хэмжилт/);
  await fireEvent(box, "layout", { nativeEvent: { layout: { width: 320, height: 200 } } });
  const option = charts.at(-1)?.option;
  expect(option?.series.map((s) => s.name)).toEqual(["bp_systolic", "bp_diastolic"]);
  expect(option?.series[0].data).toEqual([
    ["2026-10-01T08:00:00Z", 120],
    ["2026-10-08T08:00:00Z", 135],
  ]);
  // weight has one reading: no chart and no choice for it
  expect(screen.queryByRole("radio")).toBeNull();
});
