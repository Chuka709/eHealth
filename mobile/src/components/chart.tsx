import { SVGRenderer, SvgChart } from "@wuba/react-native-echarts";
import { LineChart, ScatterChart } from "echarts/charts";
import {
  DataZoomComponent,
  GridComponent,
  MarkAreaComponent,
  MarkLineComponent,
  TooltipComponent,
} from "echarts/components";
import type { EChartsCoreOption } from "echarts/core";
import * as echarts from "echarts/core";
import { useEffect, useRef, useState } from "react";
import { type LayoutChangeEvent, StyleSheet, View } from "react-native";

// What the trend charts draw (docs/06 §2): lines and points, the per-point reference band and
// critical lines (mark areas/lines), the dose steps on a second axis, event lines, pinch zoom.
// SVG renderer: no Skia native module (Phase 6.6).
echarts.use([
  SVGRenderer,
  LineChart,
  ScatterChart,
  GridComponent,
  TooltipComponent,
  DataZoomComponent,
  MarkAreaComponent,
  MarkLineComponent,
]);

type ChartInstance = ReturnType<typeof echarts.init>;

/**
 * An ECharts chart drawn with SVG. The screen builds `option` (from what the server computed -
 * the app computes nothing, rule 6); this only draws it at the width it is given. The chart is a
 * picture for sighted users: `accessibilityLabel` must say what it shows, and every value is also
 * in a list or table next to it (docs/06 UX: never colour alone).
 */
export function Chart({
  option,
  height,
  accessibilityLabel,
  testID,
}: {
  option: EChartsCoreOption;
  height: number;
  accessibilityLabel: string;
  testID?: string;
}) {
  const ref = useRef(null);
  const chart = useRef<ChartInstance | null>(null);
  const latest = useRef(option); // a re-created chart (new width) draws the latest option
  const [width, setWidth] = useState(0);

  useEffect(() => {
    if (width === 0 || ref.current === null) {
      return;
    }
    const instance = echarts.init(ref.current, undefined, { renderer: "svg", width, height });
    instance.setOption(latest.current, { notMerge: true });
    chart.current = instance;
    return () => {
      instance.dispose();
      chart.current = null;
    };
  }, [width, height]);

  useEffect(() => {
    latest.current = option;
    chart.current?.setOption(option, { notMerge: true });
  }, [option]);

  const onLayout = (e: LayoutChangeEvent) => {
    setWidth(Math.round(e.nativeEvent.layout.width));
  };

  return (
    <View
      onLayout={onLayout}
      style={[styles.box, { height }]}
      accessible
      accessibilityRole="image"
      accessibilityLabel={accessibilityLabel}
      testID={testID}
    >
      {width > 0 && <SvgChart ref={ref} />}
    </View>
  );
}

const styles = StyleSheet.create({ box: { width: "100%" } });
