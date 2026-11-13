import { fireEvent, render, screen } from "@testing-library/react-native";
import * as echarts from "echarts/core";

import { Chart } from "./chart";

type Recorded = { option: unknown; disposed: boolean };
const charts = (echarts as unknown as { __charts: Recorded[] }).__charts;

test("draws the option once it knows its width, and disposes on unmount", async () => {
  const option = { series: [{ type: "line", data: [1, 2] }] };
  const view = await render(
    <Chart option={option} height={200} accessibilityLabel="Креатинин" testID="chart" />,
  );
  const box = screen.getByTestId("chart");
  expect(box.props.accessibilityLabel).toBe("Креатинин");
  const before = charts.length;
  await view.rerender(
    <Chart option={option} height={200} accessibilityLabel="Креатинин" testID="chart" />,
  );
  // no width yet: nothing drawn
  expect(charts.length).toBe(before);
  await fireEvent(box, "layout", { nativeEvent: { layout: { width: 320, height: 200 } } });
  const drawn = charts.at(-1);
  expect(drawn?.option).toEqual(option);
  await view.unmount();
  expect(drawn?.disposed).toBe(true);
});
