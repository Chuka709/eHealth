import { useLocalSearchParams } from "expo-router";

import { AppointmentEditor } from "@/features/health/forms";

export default function AppointmentScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  return <AppointmentEditor id={id} />;
}
