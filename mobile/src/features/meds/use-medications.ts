import type { components } from "@labtrack/shared";
import { keepPreviousData, onlineManager, useMutation, useQuery } from "@tanstack/react-query";

import { currentEpoch } from "@/features/auth/session";
import {
  cancelPending,
  dismissFailed,
  enqueue,
  failedWrites,
  flush,
} from "@/features/offline/queue";
import { sendQueued } from "@/features/offline/use-local-data";
import { api } from "@/lib/api";
import { queryClient } from "@/lib/query-client";
import { newClientId } from "@/lib/random";
import { apiError } from "@/lib/use-error-text";

export type Medication = components["schemas"]["MedicationDetail"];
export type Regimen = components["schemas"]["RegimenOut"];
export type MedicationCreate = components["schemas"]["MedicationCreate"];
export type MedicationFields = components["schemas"]["MedicationIn"];
export type RegimenFields = components["schemas"]["RegimenIn"];
export type CatalogItem = components["schemas"]["CatalogItem"];
export type Intake = components["schemas"]["IntakeOut"];
export type Zones = components["schemas"]["ZonesOut"];
export type Adherence = components["schemas"]["AdherenceOut"];
export type IntakeStatus = "taken" | "skipped";

export const medicationsKey = (patientId: string) => ["medications", patientId] as const;
const zonesKey = (patientId: string) => ["timezone", patientId] as const;
const intakesKey = (patientId: string, from: string) => ["intakes", patientId, from] as const;
const adherenceKey = (patientId: string, month: string) => ["adherence", patientId, month] as const;

/** The profile's medications with their dose history; shown and planned offline. */
export function useMedications(patientId: string | undefined, { fresh = false } = {}) {
  return useQuery({
    queryKey: medicationsKey(patientId ?? ""),
    enabled: Boolean(patientId),
    refetchOnMount: fresh ? "always" : true,
    meta: { persist: true },
    queryFn: async () => {
      const { data, error } = await api.GET("/api/v1/patients/{patient_id}/medications", {
        params: { path: { patient_id: patientId ?? "" } },
      });
      if (!data) throw apiError(error);
      return data;
    },
  });
}

/** The profile's reminder time zone (Q22) - "local" medications follow it. */
export function useZones(patientId: string | undefined) {
  return useQuery({
    queryKey: zonesKey(patientId ?? ""),
    enabled: Boolean(patientId),
    meta: { persist: true },
    queryFn: async () => {
      const { data, error } = await api.GET("/api/v1/patients/{patient_id}/timezone", {
        params: { path: { patient_id: patientId ?? "" } },
      });
      if (!data) throw apiError(error);
      return data;
    },
  });
}

/** Recorded doses in [from, to) (ISO instants). */
export function useIntakes(patientId: string | undefined, from: string, to: string) {
  return useQuery({
    queryKey: intakesKey(patientId ?? "", from),
    enabled: Boolean(patientId),
    meta: { persist: true },
    placeholderData: keepPreviousData,
    queryFn: async () => {
      const { data, error } = await api.GET("/api/v1/patients/{patient_id}/intakes", {
        params: { path: { patient_id: patientId ?? "" }, query: { from, to } },
      });
      if (!data) throw apiError(error);
      return data;
    },
  });
}

/** Counts of a month's planned and recorded doses (Q23: counts only). */
export function useAdherence(patientId: string | undefined, month: string) {
  return useQuery({
    queryKey: adherenceKey(patientId ?? "", month),
    enabled: Boolean(patientId),
    queryFn: async () => {
      const { data, error } = await api.GET("/api/v1/patients/{patient_id}/adherence", {
        params: { path: { patient_id: patientId ?? "" }, query: { month } },
      });
      if (!data) throw apiError(error);
      return data;
    },
  });
}

export function useCatalogSearch(query: string) {
  const q = query.trim();
  return useQuery({
    queryKey: ["medication-catalog", q],
    enabled: q.length >= 2,
    staleTime: 60 * 60_000,
    placeholderData: keepPreviousData,
    queryFn: async () => {
      const { data, error } = await api.GET("/api/v1/medication-catalog", {
        params: { query: { q } },
      });
      if (!data) throw apiError(error);
      return data;
    },
  });
}

const refresh = (patientId: string) => {
  void queryClient.invalidateQueries({ queryKey: medicationsKey(patientId) });
  void queryClient.invalidateQueries({ queryKey: ["adherence", patientId] });
};

/** POST with the form's client_ids: a retried save finds the stored record. */
export function useCreateMedication() {
  return useMutation({
    mutationFn: async ({ patientId, body }: { patientId: string; body: MedicationCreate }) => {
      const { data, error } = await api.POST("/api/v1/patients/{patient_id}/medications", {
        params: { path: { patient_id: patientId } },
        body,
      });
      if (!data) throw apiError(error);
      return data;
    },
    onSuccess: (_, { patientId }) => refresh(patientId),
  });
}

/** PUT the whole record (stop, edit details); the dose history is never edited here. */
export function useUpdateMedication(patientId: string, medicationId: string) {
  return useMutation({
    mutationFn: async (body: MedicationFields) => {
      const { data, error } = await api.PUT(
        "/api/v1/patients/{patient_id}/medications/{medication_id}",
        { params: { path: { patient_id: patientId, medication_id: medicationId } }, body },
      );
      if (!data) throw apiError(error);
      return data;
    },
    onSuccess: () => refresh(patientId),
  });
}

/** A dose change is a new regimen row from its date on (H8): the old one stays in history. */
export function useChangeDose(patientId: string, medicationId: string) {
  return useMutation({
    mutationFn: async (body: RegimenFields) => {
      const { data, error } = await api.POST(
        "/api/v1/patients/{patient_id}/medications/{medication_id}/regimens",
        { params: { path: { patient_id: patientId, medication_id: medicationId } }, body },
      );
      if (!data) throw apiError(error);
      return data;
    },
    onSuccess: () => refresh(patientId),
  });
}

/** A coming change entered by mistake: kept in the history, marked, never in force (Q17). */
export function useVoidDose(patientId: string, medicationId: string) {
  return useMutation({
    mutationFn: async ({ regimenId, reason }: { regimenId: string; reason: string }) => {
      const { data, error } = await api.POST(
        "/api/v1/patients/{patient_id}/medications/{medication_id}/regimens/{regimen_id}/void",
        {
          params: {
            path: { patient_id: patientId, medication_id: medicationId, regimen_id: regimenId },
          },
          body: { reason },
        },
      );
      if (!data) throw apiError(error);
      return data;
    },
    onSuccess: () => refresh(patientId),
  });
}

export function useDeleteMedication(patientId: string, medicationId: string) {
  return useMutation({
    mutationFn: async () => {
      const { error, response } = await api.DELETE(
        "/api/v1/patients/{patient_id}/medications/{medication_id}",
        { params: { path: { patient_id: patientId, medication_id: medicationId } } },
      );
      if (!response.ok) throw apiError(error);
    },
    onSuccess: () => refresh(patientId),
  });
}

export type DoseRecord = {
  medicationId: string;
  scheduledAt: number; // epoch ms, a whole minute
  status: IntakeStatus;
};

const settle = (patientId: string) => {
  void queryClient.invalidateQueries({ queryKey: ["queue", "doses", patientId] });
  void queryClient.invalidateQueries({ queryKey: ["queue", "failed", patientId] });
  void queryClient.invalidateQueries({ queryKey: ["intakes", patientId] });
  void queryClient.invalidateQueries({ queryKey: ["adherence", patientId] });
};

/**
 * "Уусан" / "Алгассан": queued in the encrypted offline queue (client_id, the dose's minute)
 * and sent now when online. Shown at once from the queue itself; two devices' records of one
 * dose merge on the server - "taken" wins (H20). "full" when the queue has no room; throws
 * when the local store cannot be opened (the caller says so - never a silent no-op).
 */
export async function recordDose(
  patientId: string,
  record: DoseRecord,
): Promise<"queued" | "full"> {
  const epoch = currentEpoch();
  const clientId = newClientId();
  const body = {
    client_id: clientId,
    medication_id: record.medicationId,
    scheduled_at: new Date(record.scheduledAt).toISOString(),
    taken_at: record.status === "taken" ? new Date().toISOString() : null,
    status: record.status,
  };
  const queued = await enqueue(
    { id: clientId, method: "POST", path: `/api/v1/patients/${patientId}/intakes`, body },
    epoch,
  );
  if (!queued) return "full";
  settle(patientId);
  void flush(sendQueued)
    .catch(() => undefined)
    .finally(() => settle(patientId));
  return "queued";
}

const MINUTE = 60_000;

/**
 * "Буцаах": records still waiting in the queue are taken out; a stored record of this dose is
 * deleted on the server (a taken dose only by whoever marked it taken, or the owner - H20).
 * The stored row is found as the server keeps it - one per (medication, minute) - not by
 * the phone's client_id. Throws (the caller says so) when that needs the network and there
 * is none, or when the stored record cannot be found or deleted.
 */
export async function undoDose(
  patientId: string,
  dose: { medicationId: string; scheduledAt: number; pendingIds: string[]; stored: boolean },
): Promise<void> {
  try {
    let onServer = dose.stored;
    let wait = false;
    for (const id of dose.pendingIds) {
      const result = await cancelPending(id);
      if (result !== "removed") onServer = true;
      if (result === "sending") wait = true;
    }
    if (!onServer) return;
    if (!onlineManager.isOnline()) throw new Error("offline");
    if (wait) await flush(sendQueued);
    const { data, error } = await api.GET("/api/v1/patients/{patient_id}/intakes", {
      params: {
        path: { patient_id: patientId },
        query: {
          from: new Date(dose.scheduledAt).toISOString(),
          to: new Date(dose.scheduledAt + MINUTE).toISOString(),
          medication_id: dose.medicationId,
        },
      },
    });
    if (!data) throw apiError(error);
    const row = data.find(
      (r) =>
        r.scheduled_at !== null &&
        Math.floor(Date.parse(r.scheduled_at) / MINUTE) * MINUTE === dose.scheduledAt,
    );
    if (!row) throw new Error("not found");
    const { error: refused, response } = await api.DELETE(
      "/api/v1/patients/{patient_id}/intakes/{intake_id}",
      { params: { path: { patient_id: patientId, intake_id: row.id } } },
    );
    if (!response.ok && response.status !== 404) throw apiError(refused);
  } finally {
    settle(patientId);
  }
}

/** Dose records the server refused (kept in the queue's "failed" list until seen). */
export function useFailedDoses(patientId: string | undefined) {
  return useQuery({
    queryKey: ["queue", "failed", patientId ?? ""],
    enabled: Boolean(patientId),
    networkMode: "always",
    refetchInterval: 30_000,
    queryFn: async () => {
      const path = `/api/v1/patients/${patientId}/intakes`;
      return (await failedWrites()).filter((w) => w.path === path);
    },
  });
}

export async function dismissFailedDose(patientId: string, id: string): Promise<void> {
  await dismissFailed(id);
  void queryClient.invalidateQueries({ queryKey: ["queue", "failed", patientId] });
}
