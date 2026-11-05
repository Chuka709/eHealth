import { space } from "@labtrack/shared";
import { Stack, useRouter } from "expo-router";
import { type ReactNode, useRef, useState } from "react";
import { Alert, View } from "react-native";
import { useTranslations } from "use-intl";

import { Button } from "@/components/button";
import { FormMessage } from "@/components/form-message";
import { NavRow } from "@/components/nav-row";
import { Screen, type ScreenScroll } from "@/components/screen";
import { LoadingView, RetryView } from "@/components/state-view";
import { Paragraph } from "@/components/text";
import { ownProfile, usePatients } from "@/features/records/use-profile";
import { newClientId } from "@/lib/random";
import { useErrorText } from "@/lib/use-error-text";

import { useDeleteRecord, useRecords, useSaveRecord } from "./use-health";

type KindArg = Parameters<typeof useRecords>[0];

/** The user's own profile (health records hang on it). */
export function useOwnProfile() {
  const patients = usePatients();
  return { patients, own: ownProfile(patients.data) };
}

/** A list of one record kind: rows open the editor, "Нэмэх" opens a new one. */
export function RecordList<T extends { id: string }>({
  kind,
  route,
  row,
  addLabel,
  sort,
  header,
}: {
  kind: KindArg;
  route: string; // e.g. "/allergies"
  row: (item: T) => { label: string; hint?: string };
  addLabel: string;
  sort?: (items: T[]) => T[];
  header?: ReactNode;
}) {
  const t = useTranslations("app.health");
  const router = useRouter();
  const errorText = useErrorText();
  const { patients, own } = useOwnProfile();
  const list = useRecords(kind, own?.id);
  if (patients.isPending || (own && list.isPending)) return <LoadingView />;
  if (!own || !list.data) {
    return (
      <RetryView
        text={errorText(patients.error ?? list.error)}
        onRetry={() => void (patients.data ? list.refetch() : patients.refetch())}
      />
    );
  }
  const items = (sort ? sort(list.data as T[]) : (list.data as T[])) ?? [];
  return (
    <Screen>
      {header}
      {items.length === 0 && <Paragraph>{t("empty")}</Paragraph>}
      {items.map((item) => {
        const { label, hint } = row(item);
        return (
          <NavRow
            key={item.id}
            label={label}
            hint={hint}
            onPress={() => router.push(`${route}/${item.id}` as never)}
          />
        );
      })}
      <Button label={addLabel} onPress={() => router.push(`${route}/new` as never)} />
    </Screen>
  );
}

/**
 * The editor of one record (`id` "new" = a new one). The form keeps its draft; a retried save
 * of the same draft sends the same client_id (no duplicate), a changed draft a new one.
 */
export function RecordEditor<T extends { id: string }, D>({
  kind,
  id,
  toDraft,
  emptyDraft,
  toBody,
  errorsOf,
  children,
  titles,
  nameOf,
}: {
  kind: KindArg;
  id: string;
  /** the screen title for a new record and for an existing one */
  titles: { new: string; edit: string };
  /** how the record is named in the delete question */
  nameOf: (item: T) => string;
  toDraft: (item: T) => D;
  emptyDraft: () => D;
  /** null when the draft cannot be saved (its errors are shown) */
  toBody: (draft: D) => unknown;
  errorsOf: (draft: D) => Record<string, string>;
  children: (args: {
    draft: D;
    set: (patch: Partial<D>) => void;
    errors: Record<string, string>;
  }) => ReactNode;
}) {
  const t = useTranslations("app.health");
  const router = useRouter();
  const errorText = useErrorText();
  const { patients, own } = useOwnProfile();
  const list = useRecords(kind, own?.id, { fresh: true });
  const isNew = id === "new";
  const item = isNew ? undefined : (list.data as T[] | undefined)?.find((x) => x.id === id);

  if (patients.isPending || (own && list.isPending)) return <LoadingView />;
  if (!own || (!isNew && !item)) {
    return (
      <RetryView
        text={own && list.data ? t("notFound") : errorText(patients.error ?? list.error)}
        onRetry={() => void list.refetch()}
      />
    );
  }
  return (
    <>
      <Stack.Screen options={{ title: isNew ? titles.new : titles.edit }} />
      <EditorForm<T, D>
        name={item ? nameOf(item) : ""}
        kind={kind}
        patientId={own.id}
        item={item}
        start={item ? toDraft(item) : emptyDraft()}
        toBody={toBody}
        errorsOf={errorsOf}
        onDone={() => router.back()}
      >
        {children}
      </EditorForm>
    </>
  );
}

function EditorForm<T extends { id: string }, D>({
  name,
  kind,
  patientId,
  item,
  start,
  toBody,
  errorsOf,
  onDone,
  children,
}: {
  name: string;
  kind: KindArg;
  patientId: string;
  item: T | undefined;
  start: D;
  toBody: (draft: D) => unknown;
  errorsOf: (draft: D) => Record<string, string>;
  onDone: () => void;
  children: (args: {
    draft: D;
    set: (patch: Partial<D>) => void;
    errors: Record<string, string>;
  }) => ReactNode;
}) {
  const t = useTranslations("app.health");
  const tc = useTranslations("app.common");
  const errorText = useErrorText();
  const scroll = useRef<ScreenScroll>(null);
  const [draft, setDraft] = useState<D>(start);
  const [tried, setTried] = useState(false);
  const sent = useRef<{ key: string; id: string } | null>(null);
  const save = useSaveRecord(kind, patientId);
  const remove = useDeleteRecord(kind, patientId);
  const errors = errorsOf(draft);
  const invalid = Object.keys(errors).length > 0;
  const set = (patch: Partial<D>) => setDraft((d) => ({ ...d, ...patch }));

  const onSave = () => {
    setTried(true);
    if (invalid) {
      scroll.current?.scrollTo({ y: 0, animated: true });
      return;
    }
    const key = JSON.stringify(draft);
    if (sent.current?.key !== key) sent.current = { key, id: newClientId() };
    save.mutate(
      { id: item?.id ?? null, body: toBody(draft) as never, clientId: sent.current.id },
      { onSuccess: onDone },
    );
  };
  const onDelete = () =>
    Alert.alert(t("deleteTitle", { name }), t("deleteConfirm"), [
      { text: tc("cancel"), style: "cancel" },
      {
        text: t("deleteYes"),
        style: "destructive",
        // biome-ignore lint/style/noNonNullAssertion: shown only for a stored record
        onPress: () => remove.mutate(item!.id, { onSuccess: onDone }),
      },
    ]);
  const failure = save.error ?? remove.error;

  return (
    <Screen scrollRef={scroll}>
      {tried && invalid && <FormMessage kind="error" text={t("summary")} />}
      {failure && <FormMessage kind="error" text={errorText(failure)} />}
      {children({ draft, set, errors: tried ? errors : {} })}
      <Button label={t("save")} busy={save.isPending} onPress={onSave} />
      {item && (
        // apart from Save: a slip of the thumb never lands on Delete
        <View style={{ marginTop: space.xl }}>
          <Button label={t("delete")} variant="danger" busy={remove.isPending} onPress={onDelete} />
        </View>
      )}
    </Screen>
  );
}
