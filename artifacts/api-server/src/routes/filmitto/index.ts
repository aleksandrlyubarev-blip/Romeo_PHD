import { Router, type IRouter } from "express";
import { and, asc, eq } from "drizzle-orm";
import { z } from "zod/v4";
import {
  db,
  filmittoProjects,
  filmittoShots,
  type FilmittoProject,
  type FilmittoShot,
} from "@workspace/db";
import {
  BassitoLongLiveClient,
  ShotSpecSchema,
  generateStoryboard,
  type ShotSpec,
} from "@workspace/filmitto";

const router: IRouter = Router();
const bassito = new BassitoLongLiveClient();

// ── Request schemas ────────────────────────────────────
const CreateProjectBody = z.object({
  title: z.string().min(1).max(200),
  prompt: z.string().min(1).max(4000),
});

const ProjectIdParams = z.object({
  id: z.coerce.number().int().positive(),
});

const ShotIdParams = z.object({
  id: z.coerce.number().int().positive(),
});

const StoryboardBody = z
  .object({
    model: z.string().optional(),
    shots: z.array(ShotSpecSchema).optional(),
  })
  .optional()
  .default({});

const ShotDecisionBody = z.object({
  decision: z.enum(["accept", "reject", "reroll"]),
  note: z.string().max(1000).optional(),
});

// ── POST /api/filmitto/projects ─────────────────────────────
router.post("/filmitto/projects", async (req, res): Promise<void> => {
  const parsed = CreateProjectBody.safeParse(req.body);
  if (!parsed.success) {
    res.status(400).json({ error: parsed.error.message });
    return;
  }
  const [project] = await db
    .insert(filmittoProjects)
    .values({
      title: parsed.data.title,
      prompt: parsed.data.prompt,
      status: "draft",
    })
    .returning();
  res.status(201).json(project);
});

// ── GET /api/filmitto/projects ──────────────────────────────
router.get("/filmitto/projects", async (_req, res): Promise<void> => {
  const all = await db
    .select()
    .from(filmittoProjects)
    .orderBy(asc(filmittoProjects.createdAt));
  res.json(all);
});

// ── GET /api/filmitto/projects/:id ───────────────────────────
router.get("/filmitto/projects/:id", async (req, res): Promise<void> => {
  const params = ProjectIdParams.safeParse(req.params);
  if (!params.success) {
    res.status(400).json({ error: params.error.message });
    return;
  }
  const [project] = await db
    .select()
    .from(filmittoProjects)
    .where(eq(filmittoProjects.id, params.data.id));
  if (!project) {
    res.status(404).json({ error: "Filmitto project not found" });
    return;
  }
  const shots = await db
    .select()
    .from(filmittoShots)
    .where(eq(filmittoShots.projectId, project.id))
    .orderBy(asc(filmittoShots.orderIndex));
  res.json({ ...project, shots });
});

// ── POST /api/filmitto/projects/:id/storyboard ──────────────────────
router.post("/filmitto/projects/:id/storyboard", async (req, res): Promise<void> => {
  const params = ProjectIdParams.safeParse(req.params);
  if (!params.success) {
    res.status(400).json({ error: params.error.message });
    return;
  }
  const body = StoryboardBody.safeParse(req.body);
  if (!body.success) {
    res.status(400).json({ error: body.error.message });
    return;
  }

  const project = await loadProject(params.data.id);
  if (!project) {
    res.status(404).json({ error: "Filmitto project not found" });
    return;
  }

  let shots: ShotSpec[];
  try {
    shots = body.data.shots ??
      (await generateStoryboard(project.prompt, { model: body.data.model }));
  } catch (err) {
    res.status(502).json({
      error: `storyboard agent failed: ${err instanceof Error ? err.message : String(err)}`,
    });
    return;
  }

  await db
    .delete(filmittoShots)
    .where(eq(filmittoShots.projectId, project.id));

  const inserted = await db
    .insert(filmittoShots)
    .values(
      shots.map((shot, index) => ({
        projectId: project.id,
        orderIndex: index,
        shotId: shot.shot_id ?? `shot_${String(index + 1).padStart(2, "0")}`,
        prompt: shot.prompt,
        durationSeconds: shot.duration_seconds ?? 4.0,
        referenceImagePath: shot.reference_image_path ?? null,
        referenceClipPath: shot.reference_clip_path ?? null,
        status: "pending",
      })),
    )
    .returning();

  await db
    .update(filmittoProjects)
    .set({
      storyboard: JSON.stringify(shots),
      status: "reviewing",
      updatedAt: new Date(),
    })
    .where(eq(filmittoProjects.id, project.id));

  res.status(201).json({ project_id: project.id, shots: inserted });
});

// ── POST /api/filmitto/projects/:id/generate  (SSE) ──────────────────
router.post("/filmitto/projects/:id/generate", async (req, res): Promise<void> => {
  const params = ProjectIdParams.safeParse(req.params);
  if (!params.success) {
    res.status(400).json({ error: params.error.message });
    return;
  }
  const project = await loadProject(params.data.id);
  if (!project) {
    res.status(404).json({ error: "Filmitto project not found" });
    return;
  }

  const shots = await db
    .select()
    .from(filmittoShots)
    .where(eq(filmittoShots.projectId, project.id))
    .orderBy(asc(filmittoShots.orderIndex));

  if (shots.length === 0) {
    res.status(400).json({
      error: "Project has no shots. POST /filmitto/projects/:id/storyboard first.",
    });
    return;
  }

  res.setHeader("Content-Type", "text/event-stream");
  res.setHeader("Cache-Control", "no-cache");
  res.setHeader("Connection", "keep-alive");

  const write = (event: string, payload: Record<string, unknown>): void => {
    res.write(`data: ${JSON.stringify({ event, ...payload })}\n\n`);
  };

  await db
    .update(filmittoProjects)
    .set({ status: "generating", updatedAt: new Date() })
    .where(eq(filmittoProjects.id, project.id));

  try {
    for (const shot of shots) {
      if (shot.status === "accepted") {
        write("shot_skipped", { shot_id: shot.id, reason: "already accepted" });
        continue;
      }
      await runShotGeneration(shot, write);
    }
    await db
      .update(filmittoProjects)
      .set({ status: "reviewing", updatedAt: new Date() })
      .where(eq(filmittoProjects.id, project.id));
    write("project_done", { project_id: project.id });
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    await db
      .update(filmittoProjects)
      .set({ status: "failed", updatedAt: new Date() })
      .where(eq(filmittoProjects.id, project.id));
    write("project_failed", { project_id: project.id, error: msg });
  } finally {
    res.write(`data: ${JSON.stringify({ event: "stream_end" })}\n\n`);
    res.end();
  }
});

// ── POST /api/filmitto/shots/:id/decision ────────────────────────
router.post("/filmitto/shots/:id/decision", async (req, res): Promise<void> => {
  const params = ShotIdParams.safeParse(req.params);
  if (!params.success) {
    res.status(400).json({ error: params.error.message });
    return;
  }
  const body = ShotDecisionBody.safeParse(req.body);
  if (!body.success) {
    res.status(400).json({ error: body.error.message });
    return;
  }

  const [shot] = await db
    .select()
    .from(filmittoShots)
    .where(eq(filmittoShots.id, params.data.id));
  if (!shot) {
    res.status(404).json({ error: "Filmitto shot not found" });
    return;
  }

  const nextStatus = decisionToStatus(body.data.decision);
  const [updated] = await db
    .update(filmittoShots)
    .set({
      status: nextStatus,
      reviewNote: body.data.note ?? null,
      updatedAt: new Date(),
    })
    .where(eq(filmittoShots.id, shot.id))
    .returning();

  res.json(updated);
});

// ── Helpers ────────────────────────────────────────────
async function loadProject(id: number): Promise<FilmittoProject | undefined> {
  const [project] = await db
    .select()
    .from(filmittoProjects)
    .where(eq(filmittoProjects.id, id));
  return project;
}

function decisionToStatus(decision: "accept" | "reject" | "reroll"): string {
  if (decision === "accept") return "accepted";
  if (decision === "reject") return "rejected";
  return "pending";
}

async function runShotGeneration(
  shot: FilmittoShot,
  write: (event: string, payload: Record<string, unknown>) => void,
): Promise<void> {
  write("shot_started", { shot_id: shot.id, order: shot.orderIndex });
  await db
    .update(filmittoShots)
    .set({ status: "running", errorMessage: null, updatedAt: new Date() })
    .where(eq(filmittoShots.id, shot.id));

  let accepted;
  try {
    accepted = await bassito.generate({
      prompt: shot.prompt,
      shots: [
        {
          prompt: shot.prompt,
          duration_seconds: shot.durationSeconds,
          reference_image_path: shot.referenceImagePath ?? undefined,
          reference_clip_path: shot.referenceClipPath ?? undefined,
          shot_id: shot.shotId,
        },
      ],
    });
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    await db
      .update(filmittoShots)
      .set({ status: "failed", errorMessage: msg, updatedAt: new Date() })
      .where(eq(filmittoShots.id, shot.id));
    write("shot_failed", { shot_id: shot.id, error: msg });
    throw err;
  }

  await db
    .update(filmittoShots)
    .set({ bassitoJobId: accepted.job_id, updatedAt: new Date() })
    .where(eq(filmittoShots.id, shot.id));

  for await (const event of bassito.streamJob(accepted.job_id)) {
    if (event.type === "chunk") {
      write("shot_chunk", {
        shot_id: shot.id,
        bassito_job_id: accepted.job_id,
        chunk: event.data,
      });
    } else {
      const isOk = event.data.status === "completed";
      await db
        .update(filmittoShots)
        .set({
          status: isOk ? "review" : "failed",
          longVideoPath: event.data.long_video_path ?? null,
          errorMessage: event.data.error ?? null,
          updatedAt: new Date(),
        })
        .where(eq(filmittoShots.id, shot.id));
      write(isOk ? "shot_done" : "shot_failed", {
        shot_id: shot.id,
        bassito_job_id: accepted.job_id,
        status: event.data,
      });
      if (!isOk) {
        throw new Error(event.data.error ?? "unknown bassito failure");
      }
    }
  }
}

export default router;
