import AppKit
import CoreImage
import Foundation
import ImageIO
import UniformTypeIdentifiers
import Vision

struct IsolationConfig: Decodable {
    let identityID: String
    let anchors: [String]
    let sources: [String]
    let outputRoot: String
    let manualFaceOverrides: [String: String]?
    let manualPersonOverrides: [String: Int]?
    let rejectPersonIsolation: [String]?

    enum CodingKeys: String, CodingKey {
        case identityID = "identity_id"
        case anchors
        case sources
        case outputRoot = "output_root"
        case manualFaceOverrides = "manual_face_overrides"
        case manualPersonOverrides = "manual_person_overrides"
        case rejectPersonIsolation = "reject_person_isolation"
    }
}

struct Box: Codable {
    let x: Double
    let y: Double
    let width: Double
    let height: Double
}

struct FaceRecord: Codable {
    let faceID: String
    let box: Box
    let cropPath: String
    let anchorDistances: [Double]
    let medianDistance: Double?
    let personInstance: Int?
    let personOverlap: Double?

    enum CodingKeys: String, CodingKey {
        case faceID = "face_id"
        case box
        case cropPath = "crop_path"
        case anchorDistances = "anchor_distances"
        case medianDistance = "median_distance"
        case personInstance = "person_instance"
        case personOverlap = "person_overlap"
    }
}

struct PersonRecord: Codable {
    let instanceID: Int
    let maskPath: String
    let isolatedPath: String

    enum CodingKeys: String, CodingKey {
        case instanceID = "instance_id"
        case maskPath = "mask_path"
        case isolatedPath = "isolated_path"
    }
}

struct SourceRecord: Codable {
    let sourcePath: String
    let sourceSHA256: String
    let width: Int
    let height: Int
    let faces: [FaceRecord]
    let persons: [PersonRecord]
    let selectedFaceID: String?
    let selectedPersonInstance: Int?
    let maskPath: String?
    let isolatedPath: String?
    let overlayPath: String?
    let status: String
    let warnings: [String]

    enum CodingKeys: String, CodingKey {
        case sourcePath = "source_path"
        case sourceSHA256 = "source_sha256"
        case width
        case height
        case faces
        case persons
        case selectedFaceID = "selected_face_id"
        case selectedPersonInstance = "selected_person_instance"
        case maskPath = "mask_path"
        case isolatedPath = "isolated_path"
        case overlayPath = "overlay_path"
        case status
        case warnings
    }
}

struct Report: Codable {
    let schemaVersion: Int
    let generatedAt: String
    let identityID: String
    let detector: String
    let identityMatcher: String
    let segmenter: String
    let anchorPaths: [String]
    let records: [SourceRecord]

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case generatedAt = "generated_at"
        case identityID = "identity_id"
        case detector
        case identityMatcher = "identity_matcher"
        case segmenter
        case anchorPaths = "anchor_paths"
        case records
    }
}

enum IsolatorError: Error, CustomStringConvertible {
    case usage
    case cannotReadImage(String)
    case noAnchorFace(String)
    case cannotWrite(String)

    var description: String {
        switch self {
        case .usage:
            return "Usage: k-identity-isolator CONFIG.json"
        case .cannotReadImage(let path):
            return "Cannot read image: \(path)"
        case .noAnchorFace(let path):
            return "No face was found in anchor: \(path)"
        case .cannotWrite(let path):
            return "Cannot write output: \(path)"
        }
    }
}

let ciContext = CIContext(options: [.useSoftwareRenderer: true])

func normalizedImage(at path: String) throws -> CGImage {
    let url = URL(fileURLWithPath: path)
    guard let data = try? Data(contentsOf: url),
          let source = CGImageSourceCreateWithData(data as CFData, nil),
          let rawImage = CGImageSourceCreateImageAtIndex(source, 0, nil) else {
        throw IsolatorError.cannotReadImage(path)
    }
    let properties = CGImageSourceCopyPropertiesAtIndex(source, 0, nil) as? [CFString: Any]
    let orientation = (properties?[kCGImagePropertyOrientation] as? NSNumber)?.int32Value ?? 1
    if orientation == 1 {
        return rawImage
    }
    let image = CIImage(cgImage: rawImage).oriented(forExifOrientation: orientation)
    guard let value = ciContext.createCGImage(image, from: image.extent) else {
        throw IsolatorError.cannotReadImage(path)
    }
    return value
}

func sha256(_ path: String) throws -> String {
    let process = Process()
    process.executableURL = URL(fileURLWithPath: "/usr/bin/shasum")
    process.arguments = ["-a", "256", path]
    let pipe = Pipe()
    process.standardOutput = pipe
    process.standardError = Pipe()
    try process.run()
    process.waitUntilExit()
    let data = pipe.fileHandleForReading.readDataToEndOfFile()
    guard process.terminationStatus == 0,
          let text = String(data: data, encoding: .utf8),
          let digest = text.split(separator: " ").first else {
        throw IsolatorError.cannotReadImage(path)
    }
    return String(digest)
}

func detectFaces(in image: CGImage) throws -> [VNFaceObservation] {
    let request = VNDetectFaceRectanglesRequest()
    request.usesCPUOnly = true
    let handler = VNImageRequestHandler(cgImage: image)
    try handler.perform([request])
    return (request.results ?? []).sorted {
        if abs($0.boundingBox.minY - $1.boundingBox.minY) > 0.04 {
            return $0.boundingBox.minY > $1.boundingBox.minY
        }
        return $0.boundingBox.minX < $1.boundingBox.minX
    }
}

func cropRect(for box: CGRect, image: CGImage, padding: CGFloat = 0.18) -> CGRect {
    let width = CGFloat(image.width)
    let height = CGFloat(image.height)
    let x = box.minX * width
    let y = (1.0 - box.maxY) * height
    let w = box.width * width
    let h = box.height * height
    return CGRect(
        x: max(0, x - w * padding),
        y: max(0, y - h * padding),
        width: min(width, w * (1 + padding * 2)),
        height: min(height, h * (1 + padding * 2))
    ).intersection(CGRect(x: 0, y: 0, width: width, height: height)).integral
}

func featurePrint(for image: CGImage) throws -> VNFeaturePrintObservation {
    let request = VNGenerateImageFeaturePrintRequest()
    request.usesCPUOnly = true
    let handler = VNImageRequestHandler(cgImage: image)
    try handler.perform([request])
    guard let result = request.results?.first as? VNFeaturePrintObservation else {
        throw IsolatorError.cannotReadImage("feature print")
    }
    return result
}

func writePNG(_ image: CGImage, to path: String) throws {
    let url = URL(fileURLWithPath: path)
    try FileManager.default.createDirectory(at: url.deletingLastPathComponent(), withIntermediateDirectories: true)
    guard let destination = CGImageDestinationCreateWithURL(url as CFURL, UTType.png.identifier as CFString, 1, nil) else {
        throw IsolatorError.cannotWrite(path)
    }
    CGImageDestinationAddImage(destination, image, nil)
    guard CGImageDestinationFinalize(destination) else {
        throw IsolatorError.cannotWrite(path)
    }
}

func median(_ values: [Double]) -> Double? {
    guard !values.isEmpty else { return nil }
    let sorted = values.sorted()
    let middle = sorted.count / 2
    if sorted.count.isMultiple(of: 2) {
        return (sorted[middle - 1] + sorted[middle]) / 2.0
    }
    return sorted[middle]
}

func maskMean(_ buffer: CVPixelBuffer, in faceBox: CGRect) -> Double {
    CVPixelBufferLockBaseAddress(buffer, .readOnly)
    defer { CVPixelBufferUnlockBaseAddress(buffer, .readOnly) }
    guard let base = CVPixelBufferGetBaseAddress(buffer) else { return 0 }
    let format = CVPixelBufferGetPixelFormatType(buffer)
    let width = CVPixelBufferGetWidth(buffer)
    let height = CVPixelBufferGetHeight(buffer)
    let rowBytes = CVPixelBufferGetBytesPerRow(buffer)
    let x0 = max(0, min(width - 1, Int(faceBox.minX * CGFloat(width))))
    let x1 = max(x0 + 1, min(width, Int(faceBox.maxX * CGFloat(width))))
    let y0 = max(0, min(height - 1, Int((1.0 - faceBox.maxY) * CGFloat(height))))
    let y1 = max(y0 + 1, min(height, Int((1.0 - faceBox.minY) * CGFloat(height))))
    var total = 0.0
    var count = 0
    let step = max(1, min(x1 - x0, y1 - y0) / 12)
    for y in stride(from: y0, to: y1, by: step) {
        for x in stride(from: x0, to: x1, by: step) {
            if format == kCVPixelFormatType_OneComponent8 {
                let pointer = base.assumingMemoryBound(to: UInt8.self)
                total += Double(pointer[y * rowBytes + x]) / 255.0
            } else if format == kCVPixelFormatType_OneComponent32Float {
                let row = base.advanced(by: y * rowBytes).assumingMemoryBound(to: Float.self)
                total += Double(row[x])
            } else {
                return 0
            }
            count += 1
        }
    }
    return count == 0 ? 0 : total / Double(count)
}

func personMasks(in image: CGImage) throws -> [(Int, CVPixelBuffer, CVPixelBuffer)] {
    let request = VNGeneratePersonInstanceMaskRequest()
    request.usesCPUOnly = true
    let handler = VNImageRequestHandler(cgImage: image)
    try handler.perform([request])
    guard let observation = request.results?.first else { return [] }
    var values: [(Int, CVPixelBuffer, CVPixelBuffer)] = []
    for instance in observation.allInstances {
        let scaled = try observation.generateScaledMaskForImage(
            forInstances: IndexSet(integer: instance),
            from: handler
        )
        let analysis = try observation.generateMask(forInstances: IndexSet(integer: instance))
        values.append((instance, scaled, analysis))
    }
    return values
}

func renderedMask(_ buffer: CVPixelBuffer, width: Int, height: Int) -> CGImage? {
    let source = CIImage(cvPixelBuffer: buffer)
    let sx = CGFloat(width) / source.extent.width
    let sy = CGFloat(height) / source.extent.height
    let scaled = source.transformed(by: CGAffineTransform(scaleX: sx, y: sy))
    return ciContext.createCGImage(scaled, from: CGRect(x: 0, y: 0, width: width, height: height))
}

func isolatedAndOverlay(source: CGImage, mask: CGImage) -> (CGImage?, CGImage?) {
    let extent = CGRect(x: 0, y: 0, width: source.width, height: source.height)
    let sourceImage = CIImage(cgImage: source)
    let maskImage = CIImage(cgImage: mask)
    let clear = CIImage(color: .clear).cropped(to: extent)
    let isolated = sourceImage.applyingFilter("CIBlendWithMask", parameters: [
        kCIInputBackgroundImageKey: clear,
        kCIInputMaskImageKey: maskImage
    ])
    let red = CIImage(color: CIColor(red: 1, green: 0, blue: 0, alpha: 0.38)).cropped(to: extent)
    let maskedRed = red.applyingFilter("CIBlendWithMask", parameters: [
        kCIInputBackgroundImageKey: clear,
        kCIInputMaskImageKey: maskImage
    ])
    let overlay = maskedRed.composited(over: sourceImage)
    return (
        ciContext.createCGImage(isolated, from: extent),
        ciContext.createCGImage(overlay, from: extent)
    )
}

func slug(_ path: String) -> String {
    URL(fileURLWithPath: path).deletingPathExtension().lastPathComponent
        .replacingOccurrences(of: "[^A-Za-z0-9_-]+", with: "_", options: .regularExpression)
}

func process() throws {
    guard CommandLine.arguments.count == 2 else { throw IsolatorError.usage }
    let configURL = URL(fileURLWithPath: CommandLine.arguments[1])
    let config = try JSONDecoder().decode(IsolationConfig.self, from: Data(contentsOf: configURL))
    let root = URL(fileURLWithPath: config.outputRoot)
    try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
    let sourcePaths: [String]
    if config.sources.isEmpty, let firstAnchor = config.anchors.first {
        let directory = URL(fileURLWithPath: firstAnchor).deletingLastPathComponent()
        let allowed = Set(["jpg", "jpeg", "png", "webp", "tif", "tiff"])
        sourcePaths = try FileManager.default.contentsOfDirectory(
            at: directory,
            includingPropertiesForKeys: nil,
            options: [.skipsHiddenFiles]
        ).filter { allowed.contains($0.pathExtension.lowercased()) }
         .map(\.path)
         .sorted { $0.localizedStandardCompare($1) == .orderedAscending }
    } else {
        sourcePaths = config.sources
    }

    var anchors: [VNFeaturePrintObservation] = []
    for path in config.anchors {
        let image = try normalizedImage(at: path)
        guard let face = try detectFaces(in: image).max(by: { $0.boundingBox.width * $0.boundingBox.height < $1.boundingBox.width * $1.boundingBox.height }),
              let crop = image.cropping(to: cropRect(for: face.boundingBox, image: image)) else {
            throw IsolatorError.noAnchorFace(path)
        }
        anchors.append(try featurePrint(for: crop))
    }

    var records: [SourceRecord] = []
    for (sourceIndex, path) in sourcePaths.enumerated() {
        print("[\(sourceIndex + 1)/\(sourcePaths.count)] Detecting and isolating: \(URL(fileURLWithPath: path).lastPathComponent)")
        var warnings: [String] = []
        let image = try normalizedImage(at: path)
        let faces = try detectFaces(in: image)
        if faces.isEmpty { warnings.append("no face detected") }
        let masks: [(Int, CVPixelBuffer, CVPixelBuffer)]
        do {
            masks = try personMasks(in: image)
        } catch {
            masks = []
            warnings.append("person instance masks failed: \(error)")
        }
        if masks.isEmpty { warnings.append("no person instance mask") }
        let itemRoot = root.appendingPathComponent(slug(path))
        try FileManager.default.createDirectory(at: itemRoot, withIntermediateDirectories: true)

        var personRecords: [PersonRecord] = []
        for (instance, buffer, _) in masks {
            guard let mask = renderedMask(buffer, width: image.width, height: image.height) else { continue }
            let prefix = "person_\(String(format: "%02d", instance))"
            let personMaskPath = itemRoot.appendingPathComponent("\(prefix)_mask.png").path
            let personIsolatedPath = itemRoot.appendingPathComponent("\(prefix)_isolated.png").path
            try writePNG(mask, to: personMaskPath)
            if let isolated = isolatedAndOverlay(source: image, mask: mask).0 {
                try writePNG(isolated, to: personIsolatedPath)
            }
            personRecords.append(PersonRecord(
                instanceID: instance,
                maskPath: personMaskPath,
                isolatedPath: personIsolatedPath
            ))
        }

        var faceRecords: [FaceRecord] = []
        for (faceIndex, face) in faces.enumerated() {
            let faceID = "face_\(String(format: "%02d", faceIndex + 1))"
            let facePath = itemRoot.appendingPathComponent("\(faceID).png").path
            let rect = cropRect(for: face.boundingBox, image: image)
            guard let crop = image.cropping(to: rect) else { continue }
            try writePNG(crop, to: facePath)
            let feature = try featurePrint(for: crop)
            var distances: [Double] = []
            for anchor in anchors {
                var distance: Float = 0
                try feature.computeDistance(&distance, to: anchor)
                distances.append(Double(distance))
            }
            let bestMask = masks.map { instance, _, analysis in
                (instance, maskMean(analysis, in: face.boundingBox))
            }.max(by: { $0.1 < $1.1 })
            faceRecords.append(FaceRecord(
                faceID: faceID,
                box: Box(
                    x: Double(face.boundingBox.minX), y: Double(face.boundingBox.minY),
                    width: Double(face.boundingBox.width), height: Double(face.boundingBox.height)
                ),
                cropPath: facePath,
                anchorDistances: distances,
                medianDistance: median(distances),
                personInstance: bestMask?.0,
                personOverlap: bestMask?.1
            ))
        }

        let automaticSelection = faceRecords.compactMap { record -> FaceRecord? in
            guard record.medianDistance != nil, (record.personOverlap ?? 0) >= 0.40 else { return nil }
            return record
        }.min { ($0.medianDistance ?? .infinity) < ($1.medianDistance ?? .infinity) }
        let sourceName = URL(fileURLWithPath: path).lastPathComponent
        let overrideFaceID = config.manualFaceOverrides?[sourceName]
            ?? config.manualFaceOverrides?[slug(path)]
        let selected: FaceRecord?
        if let overrideFaceID {
            selected = faceRecords.first(where: { $0.faceID == overrideFaceID })
            if selected == nil {
                warnings.append("manual face override not found: \(overrideFaceID)")
            } else {
                warnings.append("manual face override applied: \(overrideFaceID)")
            }
        } else {
            selected = automaticSelection
        }
        let rejectPerson = (config.rejectPersonIsolation ?? []).contains(sourceName)
            || (config.rejectPersonIsolation ?? []).contains(slug(path))
        let overridePersonInstance = config.manualPersonOverrides?[sourceName]
            ?? config.manualPersonOverrides?[slug(path)]
        let selectedPersonInstance = rejectPerson ? nil : (overridePersonInstance ?? selected?.personInstance)
        if rejectPerson {
            warnings.append("person isolation intentionally rejected after review")
        } else if let overridePersonInstance {
            if masks.contains(where: { $0.0 == overridePersonInstance }) {
                warnings.append("manual person override applied: \(overridePersonInstance)")
            } else {
                warnings.append("manual person override not found: \(overridePersonInstance)")
            }
        }
        var maskPath: String?
        var isolatedPath: String?
        var overlayPath: String?
        if selected != nil, let instance = selectedPersonInstance,
           let buffer = masks.first(where: { $0.0 == instance })?.1,
           let mask = renderedMask(buffer, width: image.width, height: image.height) {
            let maskOutput = itemRoot.appendingPathComponent("subject_mask.png").path
            let isolatedOutput = itemRoot.appendingPathComponent("isolated_subject.png").path
            let overlayOutput = itemRoot.appendingPathComponent("review_overlay.png").path
            try writePNG(mask, to: maskOutput)
            if let (isolated, overlay) = Optional(isolatedAndOverlay(source: image, mask: mask)) {
                if let isolated { try writePNG(isolated, to: isolatedOutput) }
                if let overlay { try writePNG(overlay, to: overlayOutput) }
            }
            maskPath = maskOutput
            isolatedPath = isolatedOutput
            overlayPath = overlayOutput
        } else if !faces.isEmpty {
            warnings.append("no face and person-mask pair passed the automatic overlap gate")
        }
        records.append(SourceRecord(
            sourcePath: path,
            sourceSHA256: try sha256(path),
            width: image.width,
            height: image.height,
            faces: faceRecords,
            persons: personRecords,
            selectedFaceID: selected?.faceID,
            selectedPersonInstance: selectedPersonInstance,
            maskPath: maskPath,
            isolatedPath: isolatedPath,
            overlayPath: overlayPath,
            status: selected == nil ? "needs_manual_selection" : "needs_human_review",
            warnings: warnings
        ))
    }

    let formatter = ISO8601DateFormatter()
    let report = Report(
        schemaVersion: 2,
        generatedAt: formatter.string(from: Date()),
        identityID: config.identityID,
        detector: "Apple Vision VNDetectFaceRectanglesRequest",
        identityMatcher: "Apple Vision face-crop image feature prints with multi-anchor median distance",
        segmenter: "Apple Vision VNGeneratePersonInstanceMaskRequest",
        anchorPaths: config.anchors,
        records: records
    )
    let encoder = JSONEncoder()
    encoder.outputFormatting = [.prettyPrinted, .sortedKeys, .withoutEscapingSlashes]
    let reportPath = root.appendingPathComponent("isolation_report.json")
    try encoder.encode(report).write(to: reportPath, options: .atomic)
    print("Isolation report: \(reportPath.path)")
}

do {
    try process()
} catch {
    FileHandle.standardError.write(Data("Error: \(error)\n".utf8))
    exit(1)
}
