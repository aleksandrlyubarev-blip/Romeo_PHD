import { pgTable, serial, text, timestamp, integer, real } from "drizzle-orm/pg-core";
import { createInsertSchema } from "drizzle-zod";
import { z } from "zod/v4";

/**
 * One Filmitto film project: the unit a user creates and iterates on.
 * `storyboard` holds the JSON-serialized ShotSpec[] from the storyboard agent.
 */
export const filmittoProjects = pgTable("filmitto_projects", {
  id: serial("id").primaryKey(),
  title: text("title").notNull(),
  prompt: text("prompt").notNull(),
  storyboard: text("storyboard").notNull().default("[]"),
  status: text("status").notNull().default("draft"),
  // status values: draft | storyboarding | generating | reviewing | completed | failed
  finalVideoPath: text("final_video_path"),
  createdAt: timestamp("created_at", { withTimezone: true }).defaultNow().notNull(),
  updatedAt: timestamp("updated_at", { withTimezone: true }).defaultNow().notNull(),
});

/**
 * One generated shot inside a Filmitto project. Maps 1:1 to a LongLive
 * job on the bassito side via `bassitoJobId`.
 */
export const filmittoShots = pgTable("filmitto_shots", {
  id: serial("id").primaryKey(),
  projectId: integer("project_id")
    .notNull()
    .references(() => filmittoProjects.id, { onDelete: "cascade" }),
  orderIndex: integer("order_index").notNull(),
  shotId: text("shot_id").notNull(),
  prompt: text("prompt").notNull(),
  durationSeconds: real("duration_seconds").notNull().default(4.0),
  referenceImagePath: text("reference_image_path"),
  referenceClipPath: text("reference_clip_path"),
  status: text("status").notNull().default("pending"),
  // status values: pending | running | review | accepted | rejected | failed
  bassitoJobId: text("bassito_job_id"),
  longVideoPath: text("long_video_path"),
  errorMessage: text("error_message"),
  reviewNote: text("review_note"),
  createdAt: timestamp("created_at", { withTimezone: true }).defaultNow().notNull(),
  updatedAt: timestamp("updated_at", { withTimezone: true }).defaultNow().notNull(),
});

export const insertFilmittoProjectSchema = createInsertSchema(filmittoProjects).omit({
  id: true,
  createdAt: true,
  updatedAt: true,
});
export const insertFilmittoShotSchema = createInsertSchema(filmittoShots).omit({
  id: true,
  createdAt: true,
  updatedAt: true,
});

export type FilmittoProject = typeof filmittoProjects.$inferSelect;
export type FilmittoShot = typeof filmittoShots.$inferSelect;
export type InsertFilmittoProject = z.infer<typeof insertFilmittoProjectSchema>;
export type InsertFilmittoShot = z.infer<typeof insertFilmittoShotSchema>;
