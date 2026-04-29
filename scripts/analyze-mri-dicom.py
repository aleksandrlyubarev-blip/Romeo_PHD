#!/usr/bin/env python3
"""
MRI Cervical Spine DICOM Analyzer
===================================
Standalone script to analyze cervical spine MRI DICOM files using Claude Vision API.
Run directly on the machine where DICOM files are stored.

Usage:
  pip install pydicom Pillow anthropic numpy
  export ANTHROPIC_API_KEY="your-key-here"
  python analyze-mri-dicom.py /path/to/DICOM/folder

Or analyze a specific file:
  python analyze-mri-dicom.py /path/to/DICOM/folder/file
"""

import sys
import os
import io
import json
import base64
import struct
from pathlib import Path

try:
    import pydicom
    import numpy as np
    from PIL import Image
    import anthropic
except ImportError as e:
    print(f"Missing dependency: {e}")
    print("\nInstall required packages:")
    print("  pip install pydicom Pillow anthropic numpy")
    sys.exit(1)


SYSTEM_PROMPT = """You are a medical imaging analysis assistant specializing in cervical spine MRI interpretation.

IMPORTANT DISCLAIMER: You are an AI assistant. Your analysis is NOT a medical diagnosis. All findings must be reviewed and confirmed by a qualified radiologist or neurosurgeon.

Analyze the cervical spine MRI image with focus on:

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

Respond in Russian. Be detailed and specific.

Your response MUST be a valid JSON object:
{
  "overall_assessment": "Краткое резюме ключевых находок",
  "vertebrae": {
    "c3": {"status": "normal|abnormal|indeterminate", "description": "..."},
    "c4": {"status": "normal|abnormal|indeterminate", "description": "..."},
    "c5": {"status": "normal|abnormal|indeterminate", "description": "..."}
  },
  "herniation": {
    "level": "Уровни поражения",
    "severity": "none|mild|moderate|severe",
    "description": "Подробное описание"
  },
  "implant": {
    "detected": true/false,
    "integration_status": "good|partial|poor|not_applicable",
    "description": "Описание находок"
  },
  "confidence_score": 0.0-1.0,
  "additional_findings": ["..."],
  "disclaimer": "Данный анализ выполнен ИИ и не является медицинским диагнозом. Требуется подтверждение квалифицированным врачом."
}

Respond ONLY with the JSON object."""

USER_PROMPT = """Проанализируйте данный МРТ-снимок шейного отдела позвоночника. Фокус:
1. Оценка позвонков C3, C4, C5
2. Наличие и степень грыжи межпозвоночных дисков
3. Если виден хирургический имплант — оцените степень его приживления
4. Дополнительные клинически значимые находки

Верните анализ в указанном JSON-формате."""


def dicom_to_png(dicom_path: str) -> tuple[bytes, dict]:
    """Convert a DICOM file to PNG bytes and extract metadata."""
    ds = pydicom.dcmread(dicom_path)

    metadata = {
        "patient_name": str(getattr(ds, "PatientName", "Unknown")),
        "study_description": str(getattr(ds, "StudyDescription", "")),
        "series_description": str(getattr(ds, "SeriesDescription", "")),
        "modality": str(getattr(ds, "Modality", "")),
        "instance_number": int(getattr(ds, "InstanceNumber", 0)),
        "slice_location": float(getattr(ds, "SliceLocation", 0)),
        "rows": int(getattr(ds, "Rows", 0)),
        "columns": int(getattr(ds, "Columns", 0)),
    }

    pixel_array = ds.pixel_array.astype(np.float64)

    # Apply rescale
    slope = float(getattr(ds, "RescaleSlope", 1))
    intercept = float(getattr(ds, "RescaleIntercept", 0))
    pixel_array = pixel_array * slope + intercept

    # Apply windowing
    wc = getattr(ds, "WindowCenter", None)
    ww = getattr(ds, "WindowWidth", None)

    if wc is not None:
        if isinstance(wc, pydicom.multival.MultiValue):
            wc = float(wc[0])
        else:
            wc = float(wc)
    if ww is not None:
        if isinstance(ww, pydicom.multival.MultiValue):
            ww = float(ww[0])
        else:
            ww = float(ww)

    if wc is None or ww is None:
        wc = (pixel_array.min() + pixel_array.max()) / 2
        ww = pixel_array.max() - pixel_array.min()

    lower = wc - ww / 2
    upper = wc + ww / 2

    pixel_array = np.clip((pixel_array - lower) / (upper - lower) * 255, 0, 255)
    pixel_array = pixel_array.astype(np.uint8)

    img = Image.fromarray(pixel_array, mode="L")

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue(), metadata


def analyze_image(client: anthropic.Anthropic, png_bytes: bytes) -> dict:
    """Send PNG image to Claude Vision API for analysis."""
    b64 = base64.standard_b64encode(png_bytes).decode("utf-8")

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=8192,
        system=SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": b64,
                        },
                    },
                    {
                        "type": "text",
                        "text": USER_PROMPT,
                    },
                ],
            }
        ],
    )

    # Pick the first text block — vision responses can interleave non-text blocks
    # depending on tool use, and indexing [0].text blindly raises AttributeError.
    text_blocks = [b for b in message.content if getattr(b, "type", None) == "text"]
    if not text_blocks:
        raise ValueError("MRI analysis returned no text content blocks")
    text = text_blocks[0].text

    import re
    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        return json.loads(match.group(0))
    return {"raw_response": text}


def main():
    if len(sys.argv) < 2:
        print("Usage: python analyze-mri-dicom.py <DICOM_FOLDER_OR_FILE>")
        sys.exit(1)

    target = Path(sys.argv[1])
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("ERROR: Set ANTHROPIC_API_KEY environment variable")
        print("  export ANTHROPIC_API_KEY='sk-ant-...'")
        sys.exit(1)

    client = anthropic.Anthropic(api_key=api_key)

    # Collect DICOM files
    if target.is_file():
        dicom_files = [target]
    elif target.is_dir():
        dicom_files = sorted(
            [f for f in target.iterdir() if f.is_file()],
            key=lambda f: f.name.zfill(10) if f.name.isdigit() else f.name,
        )
    else:
        print(f"ERROR: {target} not found")
        sys.exit(1)

    print(f"Найдено файлов: {len(dicom_files)}")
    print("=" * 60)

    # Parse all DICOM files
    parsed = []
    for f in dicom_files:
        try:
            png_bytes, metadata = dicom_to_png(str(f))
            parsed.append({"file": f, "png": png_bytes, "meta": metadata})
        except Exception as e:
            print(f"  Пропущен {f.name}: {e}")

    if not parsed:
        print("ERROR: Не найдено валидных DICOM файлов")
        sys.exit(1)

    # Sort by instance number
    parsed.sort(key=lambda x: x["meta"].get("instance_number", 0))

    total = len(parsed)
    print(f"Успешно прочитано: {total} DICOM-файлов")
    print(f"Серия: {parsed[0]['meta'].get('series_description', 'N/A')}")
    print(f"Модальность: {parsed[0]['meta'].get('modality', 'N/A')}")
    print(f"Пациент: {parsed[0]['meta'].get('patient_name', 'N/A')}")
    print("=" * 60)

    # Select key slices (5 evenly spaced + middle)
    num_to_analyze = min(5, total)
    step = max(1, total // num_to_analyze)
    indices = list(range(0, total, step))[:num_to_analyze]
    mid = total // 2
    if mid not in indices:
        indices.append(mid)
        indices.sort()

    # Create output directory for PNG images
    images_dir = (target.parent if target.is_dir() else target.parent) / "mri_slices_png"
    images_dir.mkdir(exist_ok=True)

    # Save ALL slices as PNG (for viewing)
    print(f"\nСохраняю все {total} срезов как PNG в: {images_dir}/")
    for i, item in enumerate(parsed):
        meta = item["meta"]
        inst = meta.get("instance_number", i)
        loc = meta.get("slice_location", 0)
        png_path = images_dir / f"slice_{i:03d}_inst{inst}_loc{loc:.1f}.png"
        with open(png_path, "wb") as f:
            f.write(item["png"])
    print(f"  Сохранено {total} PNG-файлов")

    print(f"\nАнализирую {len(indices)} ключевых срезов из {total}...")
    print(f"Индексы срезов: {indices}")
    print()

    all_results = []
    for i, idx in enumerate(indices):
        item = parsed[idx]
        meta = item["meta"]
        print(f"[{i+1}/{len(indices)}] Анализ среза #{idx} "
              f"(instance={meta.get('instance_number', '?')}, "
              f"location={meta.get('slice_location', '?')})...")

        # Save analyzed slice PNG with special name
        analyzed_png = images_dir / f"ANALYZED_slice_{idx:03d}.png"
        with open(analyzed_png, "wb") as f:
            f.write(item["png"])

        try:
            result = analyze_image(client, item["png"])
            result["_slice_index"] = idx
            result["_instance_number"] = meta.get("instance_number")
            result["_slice_location"] = meta.get("slice_location")
            result["_image_path"] = str(analyzed_png)
            all_results.append(result)

            # Print summary for this slice
            oa = result.get("overall_assessment", result.get("raw_response", "N/A"))
            print(f"  → {oa[:120]}...")
            print(f"  PNG: {analyzed_png}")
            print()
        except Exception as e:
            print(f"  ОШИБКА: {e}")
            print()

    # Save full results to JSON
    output_path = target.parent / "mri_analysis_results.json" if target.is_dir() else target.parent / "mri_analysis_results.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump({
            "total_slices": total,
            "slices_analyzed": len(all_results),
            "series_description": parsed[0]["meta"].get("series_description"),
            "modality": parsed[0]["meta"].get("modality"),
            "patient_name": parsed[0]["meta"].get("patient_name"),
            "images_directory": str(images_dir),
            "results": all_results,
        }, f, ensure_ascii=False, indent=2)

    print("=" * 60)
    print(f"РЕЗУЛЬТАТЫ СОХРАНЕНЫ: {output_path}")
    print("=" * 60)

    # Print consolidated summary
    print("\n" + "=" * 60)
    print("СВОДКА АНАЛИЗА ШЕЙНОГО ОТДЕЛА ПОЗВОНОЧНИКА")
    print("=" * 60)
    for r in all_results:
        print(f"\n--- Срез #{r.get('_slice_index', '?')} ---")
        print(f"Общая оценка: {r.get('overall_assessment', 'N/A')}")

        verts = r.get("vertebrae", {})
        for v in ["c3", "c4", "c5"]:
            info = verts.get(v, {})
            print(f"  {v.upper()}: [{info.get('status', '?')}] {info.get('description', 'N/A')}")

        hern = r.get("herniation", {})
        print(f"  Грыжа: {hern.get('level', 'N/A')} — {hern.get('severity', 'N/A')}")
        print(f"    {hern.get('description', '')}")

        impl = r.get("implant", {})
        print(f"  Имплант: {'обнаружен' if impl.get('detected') else 'не обнаружен'}")
        print(f"    Приживление: {impl.get('integration_status', 'N/A')}")
        print(f"    {impl.get('description', '')}")

    print(f"\n📁 PNG-изображения всех срезов: {images_dir}/")
    print(f"📄 JSON-отчёт: {output_path}")
    print(f"\n⚠️  ДИСКЛЕЙМЕР: Данный анализ выполнен ИИ и НЕ является медицинским")
    print(f"   диагнозом. Все результаты должны быть подтверждены квалифицированным врачом.")


if __name__ == "__main__":
    main()
