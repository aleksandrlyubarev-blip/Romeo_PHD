import { boolean, integer, jsonb, pgTable, real, serial, text, timestamp } from "drizzle-orm/pg-core";
import { createInsertSchema } from "drizzle-zod";
import { z } from "zod/v4";
import { consultations } from "./pipelines";

export const inspections = pgTable("inspections", {
  id: serial("id").primaryKey(),
  inspectionId: text("inspection_id").notNull().unique(),
  imageUri: text("image_uri").notNull(),
  overallPass: boolean("overall_pass").notNull(),
  confidence: real("confidence").notNull(),
  modelVersion: text("model_version").notNull(),
  requiresHitl: boolean("requires_hitl").notNull().default(false),
  defects: jsonb("defects").notNull().default([]),
  hitlConsultationId: integer("hitl_consultation_id").references(() => consultations.id, { onDelete: "set null" }),
  createdAt: timestamp("created_at", { withTimezone: true }).defaultNow().notNull(),
});

export const insertInspectionSchema = createInsertSchema(inspections).omit({
  id: true,
  createdAt: true,
});

export type Inspection = typeof inspections.$inferSelect;
export type InsertInspection = z.infer<typeof insertInspectionSchema>;
