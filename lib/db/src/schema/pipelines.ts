import { pgTable, serial, text, timestamp, integer, real } from "drizzle-orm/pg-core";
import { createInsertSchema } from "drizzle-zod";
import { z } from "zod/v4";

export const pipelines = pgTable("pipelines", {
  id: serial("id").primaryKey(),
  name: text("name").notNull(),
  yamlContent: text("yaml_content").notNull(),
  status: text("status").notNull().default("pending"),
  nodeCount: integer("node_count").notNull().default(0),
  resolvedCount: integer("resolved_count").notNull().default(0),
  createdAt: timestamp("created_at", { withTimezone: true }).defaultNow().notNull(),
  updatedAt: timestamp("updated_at", { withTimezone: true }).defaultNow().notNull(),
});

export const pipelineNodes = pgTable("pipeline_nodes", {
  id: serial("id").primaryKey(),
  pipelineId: integer("pipeline_id").notNull().references(() => pipelines.id, { onDelete: "cascade" }),
  nodeId: text("node_id").notNull(),
  name: text("name").notNull(),
  type: text("type").notNull(),
  prompt: text("prompt"),
  dependencies: text("dependencies").notNull().default("[]"),
  status: text("status").notNull().default("PENDING"),
  output: text("output"),
  confidenceScore: real("confidence_score"),
  positionX: real("position_x").notNull().default(0),
  positionY: real("position_y").notNull().default(0),
  executedAt: timestamp("executed_at", { withTimezone: true }),
});

export const consultations = pgTable("consultations", {
  id: serial("id").primaryKey(),
  pipelineId: integer("pipeline_id").notNull().references(() => pipelines.id, { onDelete: "cascade" }),
  nodeId: text("node_id").notNull(),
  approvalId: text("approval_id").notNull().unique(),
  functionName: text("function_name").notNull(),
  arguments: text("arguments").notNull().default("{}"),
  message: text("message").notNull(),
  status: text("status").notNull().default("PENDING"),
  feedback: text("feedback"),
  createdAt: timestamp("created_at", { withTimezone: true }).defaultNow().notNull(),
});

export const telemetryEvents = pgTable("telemetry_events", {
  id: serial("id").primaryKey(),
  pipelineId: integer("pipeline_id"),
  nodeId: text("node_id"),
  eventType: text("event_type").notNull(),
  payload: text("payload").notNull().default("{}"),
  createdAt: timestamp("created_at", { withTimezone: true }).defaultNow().notNull(),
});

export const insertPipelineSchema = createInsertSchema(pipelines).omit({ id: true, createdAt: true, updatedAt: true });
export const insertPipelineNodeSchema = createInsertSchema(pipelineNodes).omit({ id: true });
export const insertConsultationSchema = createInsertSchema(consultations).omit({ id: true, createdAt: true });
export const insertTelemetrySchema = createInsertSchema(telemetryEvents).omit({ id: true, createdAt: true });

export type Pipeline = typeof pipelines.$inferSelect;
export type PipelineNode = typeof pipelineNodes.$inferSelect;
export type Consultation = typeof consultations.$inferSelect;
export type TelemetryEvent = typeof telemetryEvents.$inferSelect;
export type InsertPipeline = z.infer<typeof insertPipelineSchema>;
