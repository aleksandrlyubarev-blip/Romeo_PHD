import { anthropic } from "@workspace/integrations-anthropic-ai";

export interface VertebraAssessment {
  status: "normal" | "abnormal" | "indeterminate";
  description: string;
  measurements?: string;
}

export interface MriAnalysisResult {
  overallAssessment: string;
  vertebrae: {
    c3: VertebraAssessment;
    c4: VertebraAssessment;
    c5: VertebraAssessment;
  };
  herniation: {
    level: string;
    severity: "none" | "mild" | "moderate" | "severe";
    description: string;
  };
  implant: {
    detected: boolean;
    integrationStatus: "good" | "partial" | "poor" | "not_applicable";
    description: string;
  };
  confidenceScore: number;
  additionalFindings: string[];
  disclaimer: string;
}

const CERVICAL_SPINE_SYSTEM_PROMPT = `You are a medical imaging analysis assistant specializing in cervical spine MRI interpretation.

IMPORTANT DISCLAIMER: You are an AI assistant. Your analysis is NOT a medical diagnosis. All findings must be reviewed and confirmed by a qualified radiologist or neurosurgeon. This tool is intended to assist medical professionals, not replace them.

Your task is to analyze cervical spine MRI images with focus on:

1. VERTEBRAL ASSESSMENT (C3, C4, C5):
   - Vertebral body morphology and alignment
   - Signal intensity changes
   - Endplate integrity
   - Any compression or deformity

2. DISC HERNIATION ANALYSIS:
   - Identify disc herniation at C3-C4, C4-C5, and C5-C6 levels
   - Classify severity: none, mild (bulge), moderate (extrusion), severe (sequestration)
   - Direction of herniation (central, paracentral, foraminal)
   - Spinal canal stenosis assessment
   - Neural foraminal narrowing

3. IMPLANT INTEGRATION ASSESSMENT:
   - Detect presence of surgical implants (cages, plates, screws, artificial discs)
   - Assess osseointegration status
   - Look for subsidence, migration, or loosening signs
   - Evaluate bone growth around/through the implant
   - Classify integration: good (solid fusion), partial (incomplete fusion), poor (nonunion/pseudarthrosis)

4. ADDITIONAL FINDINGS:
   - Spinal cord signal changes (myelopathy signs)
   - Ligamentous changes
   - Facet joint pathology
   - Prevertebral soft tissue changes

Your response MUST be a valid JSON object with this exact structure:
{
  "overallAssessment": "Brief summary of key findings",
  "vertebrae": {
    "c3": { "status": "normal|abnormal|indeterminate", "description": "...", "measurements": "..." },
    "c4": { "status": "normal|abnormal|indeterminate", "description": "...", "measurements": "..." },
    "c5": { "status": "normal|abnormal|indeterminate", "description": "...", "measurements": "..." }
  },
  "herniation": {
    "level": "Affected levels, e.g. C4-C5",
    "severity": "none|mild|moderate|severe",
    "description": "Detailed herniation findings"
  },
  "implant": {
    "detected": true or false,
    "integrationStatus": "good|partial|poor|not_applicable",
    "description": "Implant findings or No implant detected"
  },
  "confidenceScore": 0.0 to 1.0,
  "additionalFindings": ["array", "of", "other", "notable", "findings"],
  "disclaimer": "This analysis is AI-generated and must be reviewed by a qualified medical professional. It is not a diagnosis."
}

Respond ONLY with the JSON object. No markdown fences, no extra text.`;

const USER_ANALYSIS_PROMPT = `Please analyze this cervical spine MRI image. Focus on:
1. Assessment of vertebrae C3, C4, and C5
2. Any disc herniation present and its severity
3. If a surgical implant is visible, evaluate its integration status
4. Any additional clinically relevant findings

Return your analysis as the specified JSON structure.`;

export async function analyzeMriImage(
  imageBase64: string,
  mimeType: "image/jpeg" | "image/png",
): Promise<MriAnalysisResult> {
  const message = await anthropic.messages.create({
    model: "claude-sonnet-4-6",
    max_tokens: 8192,
    system: CERVICAL_SPINE_SYSTEM_PROMPT,
    messages: [
      {
        role: "user",
        content: [
          {
            type: "image",
            source: {
              type: "base64",
              media_type: mimeType,
              data: imageBase64,
            },
          },
          {
            type: "text",
            text: USER_ANALYSIS_PROMPT,
          },
        ],
      },
    ],
  });

  const content = message.content[0];
  if (content.type !== "text") {
    throw new Error("MRI analysis produced no text output");
  }

  try {
    const jsonMatch = content.text.match(/\{[\s\S]*\}/);
    if (!jsonMatch) throw new Error("No structured JSON found in analysis response");
    return JSON.parse(jsonMatch[0]) as MriAnalysisResult;
  } catch {
    throw new Error("Failed to parse MRI analysis response as JSON");
  }
}
