import { useRouter } from "expo-router";

import { TransplantWizard } from "@/features/records/transplant-wizard";

export default function NewTransplantScreen() {
  const router = useRouter();
  return <TransplantWizard onDone={() => router.back()} />;
}
