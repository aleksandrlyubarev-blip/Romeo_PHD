import dicomParser from "dicom-parser";
import { PNG } from "pngjs";

export interface DicomMetadata {
  patientName?: string;
  studyDescription?: string;
  seriesDescription?: string;
  modality?: string;
  rows: number;
  columns: number;
  bitsAllocated: number;
  bitsStored: number;
  pixelRepresentation: number;
  windowCenter?: number;
  windowWidth?: number;
  sliceLocation?: number;
  instanceNumber?: number;
  rescaleIntercept: number;
  rescaleSlope: number;
}

export interface DicomConversionResult {
  pngBuffer: Buffer;
  metadata: DicomMetadata;
}

function getString(dataSet: dicomParser.DataSet, tag: string): string | undefined {
  const element = dataSet.elements[tag];
  if (!element) return undefined;
  return dataSet.string(tag)?.trim();
}

function getNumber(dataSet: dicomParser.DataSet, tag: string): number | undefined {
  const val = getString(dataSet, tag);
  if (val === undefined) return undefined;
  const num = parseFloat(val);
  return isNaN(num) ? undefined : num;
}

function extractMetadata(dataSet: dicomParser.DataSet): DicomMetadata {
  return {
    patientName: getString(dataSet, "x00100010"),
    studyDescription: getString(dataSet, "x00081030"),
    seriesDescription: getString(dataSet, "x0008103e"),
    modality: getString(dataSet, "x00080060"),
    rows: dataSet.uint16("x00280010") ?? 0,
    columns: dataSet.uint16("x00280011") ?? 0,
    bitsAllocated: dataSet.uint16("x00280100") ?? 16,
    bitsStored: dataSet.uint16("x00280101") ?? 16,
    pixelRepresentation: dataSet.uint16("x00280103") ?? 0,
    windowCenter: getNumber(dataSet, "x00281050"),
    windowWidth: getNumber(dataSet, "x00281051"),
    sliceLocation: getNumber(dataSet, "x00201041"),
    instanceNumber: getNumber(dataSet, "x00200013"),
    rescaleIntercept: getNumber(dataSet, "x00281052") ?? 0,
    rescaleSlope: getNumber(dataSet, "x00281053") ?? 1,
  };
}

function getPixelData(dataSet: dicomParser.DataSet, metadata: DicomMetadata): Int16Array | Uint16Array {
  const pixelDataElement = dataSet.elements["x7fe00010"];
  if (!pixelDataElement) {
    throw new Error("No pixel data found in DICOM file");
  }

  const { byteArray } = dataSet;
  const offset = pixelDataElement.dataOffset;
  const length = pixelDataElement.length;

  if (metadata.bitsAllocated === 16) {
    // Copy into a fresh, aligned ArrayBuffer — typed-array views require
    // alignment, but `byteArray.byteOffset + offset` may be odd which would
    // throw a RangeError when constructing Int16Array/Uint16Array directly.
    const aligned = new Uint8Array(
      byteArray.buffer,
      byteArray.byteOffset + offset,
      length,
    ).slice().buffer;
    if (metadata.pixelRepresentation === 1) {
      return new Int16Array(aligned);
    }
    return new Uint16Array(aligned);
  }

  // 8-bit: read bytes into a Uint8Array source view, then promote to Uint16Array
  const src = new Uint8Array(byteArray.buffer, byteArray.byteOffset + offset, length);
  const data = new Uint16Array(length);
  for (let i = 0; i < length; i++) {
    data[i] = src[i];
  }
  return data;
}

function applyWindowing(
  pixelData: Int16Array | Uint16Array,
  metadata: DicomMetadata,
): Uint8Array {
  const { rescaleSlope, rescaleIntercept } = metadata;

  // Apply rescale to get Hounsfield units
  const rescaled = new Float64Array(pixelData.length);
  let minVal = Infinity;
  let maxVal = -Infinity;
  for (let i = 0; i < pixelData.length; i++) {
    const val = pixelData[i] * rescaleSlope + rescaleIntercept;
    rescaled[i] = val;
    if (val < minVal) minVal = val;
    if (val > maxVal) maxVal = val;
  }

  // Use DICOM window center/width if available, otherwise auto-window
  let wc = metadata.windowCenter ?? (minVal + maxVal) / 2;
  let ww = metadata.windowWidth ?? (maxVal - minVal);
  if (ww <= 0) ww = 1;

  const lower = wc - ww / 2;
  const upper = wc + ww / 2;

  const output = new Uint8Array(pixelData.length);
  for (let i = 0; i < rescaled.length; i++) {
    const val = rescaled[i];
    if (val <= lower) {
      output[i] = 0;
    } else if (val >= upper) {
      output[i] = 255;
    } else {
      output[i] = Math.round(((val - lower) / (upper - lower)) * 255);
    }
  }

  return output;
}

export function parseDicom(buffer: Buffer): DicomConversionResult {
  const byteArray = new Uint8Array(buffer);
  const dataSet = dicomParser.parseDicom(byteArray);
  const metadata = extractMetadata(dataSet);

  if (metadata.rows === 0 || metadata.columns === 0) {
    throw new Error("DICOM file has no image dimensions (rows/columns)");
  }

  const pixelData = getPixelData(dataSet, metadata);
  const grayscale = applyWindowing(pixelData, metadata);

  // Create PNG from grayscale data
  const png = new PNG({ width: metadata.columns, height: metadata.rows });
  for (let i = 0; i < grayscale.length; i++) {
    const val = grayscale[i];
    const idx = i * 4;
    png.data[idx] = val;     // R
    png.data[idx + 1] = val; // G
    png.data[idx + 2] = val; // B
    png.data[idx + 3] = 255; // A
  }

  const pngBuffer = PNG.sync.write(png);

  return { pngBuffer, metadata };
}

export function isDicomFile(buffer: Buffer): boolean {
  // DICOM files have "DICM" magic at offset 128
  if (buffer.length > 132) {
    const magic = buffer.slice(128, 132).toString("ascii");
    if (magic === "DICM") return true;
  }
  // Some DICOM files lack the preamble — try parsing the first tag
  // Group 0008 is common for DICOM
  if (buffer.length > 4) {
    const group = buffer.readUInt16LE(0);
    return group === 0x0008 || group === 0x0002;
  }
  return false;
}
