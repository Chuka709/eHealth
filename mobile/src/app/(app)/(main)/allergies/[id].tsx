import { useLocalSearchParams } from "expo-router";

import { AllergyEditor } from "@/features/health/forms";

export default function AllergyScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  return <AllergyEditor id={id} />;
}
