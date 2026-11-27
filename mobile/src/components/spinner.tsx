import { useEffect, useId, useRef, useState } from "react";
import {
  AccessibilityInfo,
  Animated,
  type ColorValue,
  Easing,
  StyleSheet,
  View,
} from "react-native";
import Svg, { Circle, Defs, LinearGradient, Stop } from "react-native-svg";

import { usePalette } from "@/theme/use-palette";

export const SPINNER_LARGE = 48;
const SIZES = { small: 20, large: SPINNER_LARGE } as const;
// a steady, unhurried turn; the core breathes at about a resting heart rate
const TURN_MS = 1000;
const BREATH_MS = 900;
// how much of the ring the comet covers
const ARC = 0.72;

/**
 * The app's one loading indicator (user request 2026.11.27: elegant, the same everywhere): a
 * faint ring with a brand-coloured comet sweeping round it - a rounded head fading into its tail
 * - and, at full size, a soft core that breathes like a heartbeat. Decorative: the words next to
 * it (or the button's label) are what a screen reader says. With "reduce motion" on it stands
 * still.
 */
export function Spinner({
  size = "small",
  color,
  testID,
}: {
  size?: keyof typeof SIZES;
  color?: ColorValue;
  testID?: string;
}) {
  const p = usePalette();
  const tint = color ?? p.primary;
  const d = SIZES[size];
  const stroke = size === "large" ? 4 : 2.5;
  const r = (d - stroke) / 2;
  const length = 2 * Math.PI * r;
  const gradient = `spin${useId().replace(/[^a-zA-Z0-9]/g, "")}`;
  const reduceMotion = useReduceMotion();
  const turn = useRef(new Animated.Value(0)).current;
  const breath = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    if (reduceMotion) return;
    const spin = Animated.loop(
      Animated.timing(turn, {
        toValue: 1,
        duration: TURN_MS,
        easing: Easing.linear,
        useNativeDriver: true,
      }),
    );
    const beat = Animated.loop(
      Animated.sequence([
        Animated.timing(breath, {
          toValue: 1,
          duration: BREATH_MS / 2,
          easing: Easing.out(Easing.quad),
          useNativeDriver: true,
        }),
        Animated.timing(breath, {
          toValue: 0,
          duration: BREATH_MS / 2,
          easing: Easing.in(Easing.quad),
          useNativeDriver: true,
        }),
      ]),
    );
    spin.start();
    if (size === "large") beat.start();
    return () => {
      spin.stop();
      beat.stop();
    };
  }, [reduceMotion, turn, breath, size]);

  const rotate = turn.interpolate({ inputRange: [0, 1], outputRange: ["0deg", "360deg"] });
  const core = d * 0.34;

  return (
    <View
      testID={testID}
      accessible={false}
      importantForAccessibility="no-hide-descendants"
      accessibilityElementsHidden
      style={[styles.box, { width: d, height: d }]}
    >
      {size === "large" && (
        <Animated.View
          style={[
            styles.core,
            {
              width: core,
              height: core,
              borderRadius: core / 2,
              backgroundColor: tint,
              opacity: breath.interpolate({ inputRange: [0, 1], outputRange: [0.18, 0.42] }),
              transform: [
                { scale: breath.interpolate({ inputRange: [0, 1], outputRange: [0.7, 1] }) },
              ],
            },
          ]}
        />
      )}
      <Svg width={d} height={d} style={StyleSheet.absoluteFill}>
        <Circle
          cx={d / 2}
          cy={d / 2}
          r={r}
          stroke={tint}
          strokeOpacity={0.14}
          strokeWidth={stroke}
          fill="none"
        />
      </Svg>
      <Animated.View
        style={[
          StyleSheet.absoluteFill,
          { transform: [{ rotate: reduceMotion ? "0deg" : rotate }] },
        ]}
      >
        <Svg width={d} height={d}>
          <Defs>
            {/* the arc runs clockwise from the top: its leading end (lower left) is solid, the
                tail back at the top fades out */}
            <LinearGradient id={gradient} x1="1" y1="0" x2="0" y2="1">
              <Stop offset="0.15" stopColor={tint} stopOpacity={0} />
              <Stop offset="0.85" stopColor={tint} stopOpacity={1} />
            </LinearGradient>
          </Defs>
          <Circle
            cx={d / 2}
            cy={d / 2}
            r={r}
            stroke={`url(#${gradient})`}
            strokeWidth={stroke}
            strokeLinecap="round"
            strokeDasharray={`${length * ARC} ${length}`}
            fill="none"
            transform={`rotate(-90 ${d / 2} ${d / 2})`}
          />
        </Svg>
      </Animated.View>
    </View>
  );
}

function useReduceMotion(): boolean {
  const [reduce, setReduce] = useState(false);
  useEffect(() => {
    let live = true;
    void AccessibilityInfo.isReduceMotionEnabled()
      .then((on) => {
        if (live) setReduce(on);
      })
      .catch(() => undefined);
    const sub = AccessibilityInfo.addEventListener("reduceMotionChanged", setReduce);
    return () => {
      live = false;
      sub.remove();
    };
  }, []);
  return reduce;
}

const styles = StyleSheet.create({
  box: { alignItems: "center", justifyContent: "center" },
  core: { position: "absolute" },
});
