import { Redirect } from "expo-router";

import { useSession } from "@/features/auth/use-session";
import { useLocked } from "@/features/lock/lock-store";

/** Anchor route: sends "/" (launch, or a guard that just flipped) to the right group. */
export default function Index() {
  const status = useSession();
  const locked = useLocked();
  if (status === "signedIn") return <Redirect href={locked ? "/lock" : "/home"} />;
  return <Redirect href={status === "notice" ? "/notice" : "/welcome"} />;
}
