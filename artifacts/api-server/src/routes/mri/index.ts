import { Router, type IRouter } from "express";
import multer from "multer";
import { db, mriAnalyses } from "@workspace/db";
import { analyzeMriImage } from "../../lib/mri-analyzer";

const router: IRouter = Router();

const upload = multer({
  storage: multer.memoryStorage(),
  limits: {
    fileSize: 20 * 1024 * 1024, // 20MB
  },
  fileFilter: (_req, file, cb) => {
    if (file.mimetype === "image/jpeg" || file.mimetype === "image/png") {
      cb(null, true);
    } else {
      cb(new Error("Only JPEG and PNG files are accepted for MRI analysis"));
    }
  },
});

// ─── Analyze MRI Image ──────────────────────────────────────────────────────
router.post("/mri/analyze", upload.single("image"), async (req, res): Promise<void> => {
  if (!req.file) {
    res.status(400).json({ error: "No image file provided. Send a file in the 'image' field." });
    return;
  }

  const imageBase64 = req.file.buffer.toString("base64");
  const mimeType = req.file.mimetype as "image/jpeg" | "image/png";

  try {
    const result = await analyzeMriImage(imageBase64, mimeType);

    const [saved] = await db
      .insert(mriAnalyses)
      .values({
        fileName: req.file.originalname,
        mimeType,
        imageSizeBytes: req.file.size,
        overallAssessment: result.overallAssessment,
        findings: JSON.stringify(result),
        c3Assessment: result.vertebrae.c3.description,
        c4Assessment: result.vertebrae.c4.description,
        c5Assessment: result.vertebrae.c5.description,
        herniationLevel: result.herniation.level,
        herniationSeverity: result.herniation.severity,
        implantDetected: result.implant.detected ? "yes" : "no",
        implantIntegrationStatus: result.implant.integrationStatus,
        confidenceScore: result.confidenceScore,
        rawLlmResponse: JSON.stringify(result),
      })
      .returning();

    res.json({
      id: saved.id,
      ...result,
      createdAt: saved.createdAt,
    });
  } catch (err) {
    const errMsg = err instanceof Error ? err.message : "Unknown error during MRI analysis";
    res.status(500).json({ error: errMsg });
  }
});

export default router;
