import { Router, type IRouter } from "express";
import multer from "multer";
import { db, mriAnalyses } from "@workspace/db";
import { analyzeMriImage, type MriAnalysisResult } from "../../lib/mri-analyzer";
import { parseDicom, isDicomFile } from "../../lib/dicom-converter";

const router: IRouter = Router();

const upload = multer({
  storage: multer.memoryStorage(),
  limits: {
    fileSize: 50 * 1024 * 1024, // 50MB per file
  },
});

const uploadSeries = multer({
  storage: multer.memoryStorage(),
  limits: {
    fileSize: 50 * 1024 * 1024,
    files: 300,
  },
});

async function processFile(file: Express.Multer.File): Promise<{
  imageBase64: string;
  mimeType: "image/jpeg" | "image/png";
  dicomMetadata?: ReturnType<typeof parseDicom>["metadata"];
}> {
  // Check if it's a DICOM file (by content, not mimetype — DICOM files often come as application/octet-stream)
  if (isDicomFile(file.buffer)) {
    const { pngBuffer, metadata } = parseDicom(file.buffer);
    return {
      imageBase64: pngBuffer.toString("base64"),
      mimeType: "image/png",
      dicomMetadata: metadata,
    };
  }

  // Regular image file
  if (file.mimetype === "image/jpeg" || file.mimetype === "image/png") {
    return {
      imageBase64: file.buffer.toString("base64"),
      mimeType: file.mimetype as "image/jpeg" | "image/png",
    };
  }

  throw new Error(`Unsupported file type: ${file.mimetype}. Accepted: DICOM, JPEG, PNG.`);
}

async function saveAnalysis(
  fileName: string,
  mimeType: string,
  fileSize: number,
  result: MriAnalysisResult,
) {
  const [saved] = await db
    .insert(mriAnalyses)
    .values({
      fileName,
      mimeType,
      imageSizeBytes: fileSize,
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
  return saved;
}

// ─── Analyze Single MRI Image (DICOM, JPEG, or PNG) ────────────────────────
router.post("/mri/analyze", upload.single("image"), async (req, res): Promise<void> => {
  if (!req.file) {
    res.status(400).json({ error: "No image file provided. Send a file in the 'image' field." });
    return;
  }

  try {
    const { imageBase64, mimeType, dicomMetadata } = await processFile(req.file);
    const result = await analyzeMriImage(imageBase64, mimeType);

    const saved = await saveAnalysis(
      req.file.originalname,
      req.file.mimetype,
      req.file.size,
      result,
    );

    res.json({
      id: saved.id,
      ...result,
      ...(dicomMetadata ? { dicomMetadata } : {}),
      createdAt: saved.createdAt,
    });
  } catch (err) {
    const errMsg = err instanceof Error ? err.message : "Unknown error during MRI analysis";
    res.status(500).json({ error: errMsg });
  }
});

// ─── Analyze DICOM Series (multiple files) ──────────────────────────────────
router.post("/mri/analyze-series", uploadSeries.array("images", 300), async (req, res): Promise<void> => {
  const files = req.files as Express.Multer.File[] | undefined;
  if (!files || files.length === 0) {
    res.status(400).json({ error: "No files provided. Send DICOM files in the 'images' field." });
    return;
  }

  try {
    // Parse all DICOM files and sort by instance number / slice location
    const parsed = [];
    for (const file of files) {
      try {
        const { pngBuffer, metadata } = parseDicom(file.buffer);
        parsed.push({ file, pngBuffer, metadata });
      } catch {
        // Skip non-DICOM files silently
      }
    }

    if (parsed.length === 0) {
      res.status(400).json({ error: "No valid DICOM files found in the uploaded series." });
      return;
    }

    // Sort by instance number or slice location
    parsed.sort((a, b) => {
      const aNum = a.metadata.instanceNumber ?? a.metadata.sliceLocation ?? 0;
      const bNum = b.metadata.instanceNumber ?? b.metadata.sliceLocation ?? 0;
      return aNum - bNum;
    });

    // Select key slices for analysis (mid-sagittal views are most informative)
    // Pick ~5 evenly spaced slices from the series to cover the cervical region
    const totalSlices = parsed.length;
    const numToAnalyze = Math.min(5, totalSlices);
    const step = Math.max(1, Math.floor(totalSlices / numToAnalyze));
    const selectedIndices: number[] = [];
    for (let i = 0; i < totalSlices && selectedIndices.length < numToAnalyze; i += step) {
      selectedIndices.push(i);
    }
    // Always include the middle slice
    const midIdx = Math.floor(totalSlices / 2);
    if (!selectedIndices.includes(midIdx)) {
      selectedIndices.push(midIdx);
      selectedIndices.sort((a, b) => a - b);
    }

    const results = [];
    for (const idx of selectedIndices) {
      const slice = parsed[idx];
      const imageBase64 = slice.pngBuffer.toString("base64");
      const result = await analyzeMriImage(imageBase64, "image/png");

      const saved = await saveAnalysis(
        slice.file.originalname,
        "application/dicom",
        slice.file.size,
        result,
      );

      results.push({
        id: saved.id,
        sliceIndex: idx,
        instanceNumber: slice.metadata.instanceNumber,
        sliceLocation: slice.metadata.sliceLocation,
        seriesDescription: slice.metadata.seriesDescription,
        ...result,
        createdAt: saved.createdAt,
      });
    }

    res.json({
      totalSlicesReceived: totalSlices,
      slicesAnalyzed: results.length,
      seriesDescription: parsed[0].metadata.seriesDescription,
      modality: parsed[0].metadata.modality,
      patientName: parsed[0].metadata.patientName,
      results,
    });
  } catch (err) {
    const errMsg = err instanceof Error ? err.message : "Unknown error during series analysis";
    res.status(500).json({ error: errMsg });
  }
});

export default router;
