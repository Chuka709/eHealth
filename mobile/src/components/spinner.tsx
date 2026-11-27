import { useEffect, useRef, useState } from "react";
import {
  AccessibilityInfo,
  Animated,
  type ColorValue,
  Easing,
  StyleSheet,
  View,
} from "react-native";

import { usePalette } from "@/theme/use-palette";

const SIZES = { small: 20, large: 44 } as const;
// one turn eases in and out (a calm sweep, not a mechanical spin); a second arc trails it
const TURN_MS = 1100;

/**
 * The app's one loading indicator (user request 2026.11.27, replaces ActivityIndicator): a faint
 * ring with a brand-coloured arc sweeping around it. Decorative - the words next to it (or the
 * button's label) are what a screen reader says. With "reduce motion" on it stands still.
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
  const stroke = Math.max(2, Math.round(d / 9));
  const reduceMotion = useReduceMotion();
  const turn = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    if (reduceMotion) return;
    const loop = Animated.loop(
      Animated.timing(turn, {
        toValue: 1,
        duration: TURN_MS,
        easing: Easing.bezier(0.45, 0.05, 0.55, 0.95),
        useNativeDriver: true,
      }),
    );
    loop.start();
    return () => loop.stop();
  }, [reduceMotion, turn]);

  const rotate = turn.interpolate({ inputRange: [0, 1], outputRange: ["0deg", "360deg"] });
  // the trailing arc lags a little behind, so the sweep looks like it stretches and catches up
  const trail = turn.interpolate({
    inputRange: [0, 0.5, 1],
    outputRange: ["-40deg", "150deg", "320deg"],
  });
  const ring = { width: d, height: d, borderRadius: d / 2, borderWidth: stroke };
  const arc = {
    borderTopColor: tint,
    borderRightColor: "transparent",
    borderBottomColor: "transparent",
    borderLeftColor: "transparent",
  } as const;

  return (
    <View
      testID={testID}
      accessible={false}
      importantForAccessibility="no-hide-descendants"
      accessibilityElementsHidden
      style={{ width: d, height: d }}
    >
      <View style={[styles.layer, ring, { borderColor: tint, opacity: 0.22 }]} />
      <Animated.View
        style={[styles.layer, ring, arc, { opacity: 0.6, transform: [{ rotate: trail }] }]}
      />
      <Animated.View
        style={[
          styles.layer,
          ring,
          arc,
          { borderRightColor: tint, transform: [{ rotate: reduceMotion ? "45deg" : rotate }] },
        ]}
      />
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
  layer: { position: "absolute", top: 0, left: 0 },
});
