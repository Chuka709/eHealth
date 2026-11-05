import { useLocalSearchParams } from "expo-router";

import { ContactEditor } from "@/features/health/forms";

export default function ContactScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  return <ContactEditor id={id} />;
}
