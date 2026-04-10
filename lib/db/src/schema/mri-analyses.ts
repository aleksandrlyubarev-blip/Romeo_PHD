import { pgTable, serial, text, timestamp, integer, real } from "drizzle-orm/pg-core";
import { createInsertSchema } from "drizzle-zod";
import { z } from "zod/v4";

export const mriAnalyses = pgTable("mri_analyses", {
  id: serial("id").primaryKey(),
  fileName: text("file_name").notNull(),
  mimeType: text("mime_type").notNull(),
  imageSizeBytes: integer("image_size_bytes").notNull(),
  overallAssessment: text("overall_assessment").notNull(),
  findings: text("findings").notNull().default("{}"),
  c3Assessment: text("c3_assessment"),
  c4Assessment: text("c4_assessment"),
  c5Assessment: text("c5_assessment"),
  herniationLevel: text("herniation_level"),
  herniationSeverity: text("herniation_severity"),
  implantDetected: text("implant_detected"),
  implantIntegrationStatus: text("implant_integration_status"),
  confidenceScore: real("confidence_score"),
  rawLlmResponse: text("raw_llm_response"),
  createdAt: timestamp("created_at", { withTimezone: true }).defaultNow().notNull(),
});

export const insertMriAnalysisSchema = createInsertSchema(mriAnalyses).omit({ id: true, createdAt: true });
export type MriAnalysis = typeof mriAnalyses.$inferSelect;
export type InsertMriAnalysis = z.infer<typeof insertMriAnalysisSchema>;
