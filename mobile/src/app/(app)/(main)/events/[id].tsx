import { useLocalSearchParams } from "expo-router";

import { EventEditor } from "@/features/health/forms";

export default function EventScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  return <EventEditor id={id} />;
}
