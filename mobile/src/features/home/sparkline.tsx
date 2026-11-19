import { View } from "react-native";
import Svg, { Circle, Polyline } from "react-native-svg";

import { usePalette } from "@/theme/use-palette";

import type { DashboardCard } from "./use-dashboard";

const W = 96;
const H = 32;
const PAD = 3;

/**
 * A card's last values as a small line (decorative: the card says the value, its range and
 * the change in words). Drawn straight with SVG - no chart library on Home (its p95, Phase 6
 * DoD). The points are the server's (one unit, oldest first); a "< x" bound is hollow.
 */
export function Sparkline({ spark }: { spark: DashboardCard["spark"] }) {
  const p = usePalette();
  if (spark.length < 2) return null;
  const values = spark.map((s) => Number(s.value));
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const x = (i: number) => PAD + (i * (W - 2 * PAD)) / (values.length - 1);
  const y = (v: number) => H - PAD - ((v - min) * (H - 2 * PAD)) / span;
  const last = spark.at(-1);
  const lastValue = values[values.length - 1];
  return (
    <View accessible={false} importantForAccessibility="no-hide-descendants">
      <Svg width={W} height={H}>
        <Polyline
          points={values.map((v, i) => `${x(i)},${y(v)}`).join(" ")}
          fill="none"
          stroke={p.primary}
          strokeWidth={1.5}
        />
        <Circle
          cx={x(values.length - 1)}
          cy={y(lastValue)}
          r={3}
          fill={last?.comparator ? p.surface : p.primary}
          stroke={p.primary}
        />
      </Svg>
    </View>
  );
}
