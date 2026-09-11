import Foundation
import ImageIO
import Vision

private struct FrameInput: Decodable {
    let path: String
    let timestampSeconds: Double
    enum CodingKeys: String, CodingKey { case path; case timestampSeconds = "timestamp_seconds" }
}
private struct Box: Codable { let x: Double; let y: Double; let width: Double; let height: Double }
private struct Sample: Codable {
    let timestampSeconds: Double; let framePath: String; let box: Box; let confidence: Float; let status: String
    enum CodingKeys: String, CodingKey {
        case timestampSeconds = "timestamp_seconds"; case framePath = "frame_path"; case box; case confidence; case status
    }
}
private struct Result: Codable {
    let schemaVersion = 1; let coordinateSpace = "vision_normalized_lower_left"; let inference = "VNTrackObjectRequest"
    let samples: [Sample]
    enum CodingKeys: String, CodingKey { case schemaVersion = "schema_version"; case coordinateSpace = "coordinate_space"; case inference; case samples }
}
private func parseBox(_ text: String) throws -> CGRect {
    let values = text.split(separator: ",").compactMap { Double($0) }
    guard values.count == 4 else { throw NSError(domain: "SceneFactory", code: 2, userInfo: [NSLocalizedDescriptionKey: "bbox must be x,y,width,height"]) }
    let box = CGRect(x: values[0], y: values[1], width: values[2], height: values[3])
    guard box.minX >= 0, box.minY >= 0, box.maxX <= 1, box.maxY <= 1 else { throw NSError(domain: "SceneFactory", code: 2, userInfo: [NSLocalizedDescriptionKey: "bbox outside normalized frame"]) }
    return box
}
private func image(_ path: String) throws -> CGImage {
    guard let source = CGImageSourceCreateWithURL(URL(fileURLWithPath: path) as CFURL, nil),
          let image = CGImageSourceCreateImageAtIndex(source, 0, nil) else {
        throw NSError(domain: "SceneFactory", code: 1, userInfo: [NSLocalizedDescriptionKey: "Cannot read \(path)"])
    }
    return image
}

guard CommandLine.arguments.count == 4 else {
    fputs("Usage: track_object_frames INPUT.json X,Y,WIDTH,HEIGHT OUTPUT.json\n", stderr); exit(2)
}
do {
    let frames = try JSONDecoder().decode([FrameInput].self, from: Data(contentsOf: URL(fileURLWithPath: CommandLine.arguments[1])))
    guard !frames.isEmpty else { throw NSError(domain: "SceneFactory", code: 2, userInfo: [NSLocalizedDescriptionKey: "No frames"]) }
    let initial = try parseBox(CommandLine.arguments[2])
    var observation = VNDetectedObjectObservation(boundingBox: initial)
    let handler = VNSequenceRequestHandler()
    var samples: [Sample] = []
    for (index, frame) in frames.enumerated() {
        if index == 0 {
            samples.append(Sample(timestampSeconds: frame.timestampSeconds, framePath: frame.path, box: Box(x: initial.minX, y: initial.minY, width: initial.width, height: initial.height), confidence: 1, status: "manual_initialization"))
            continue
        }
        let request = VNTrackObjectRequest(detectedObjectObservation: observation)
        request.trackingLevel = .accurate
        request.usesCPUOnly = true
        try handler.perform([request], on: try image(frame.path), orientation: .up)
        guard let next = request.results?.first as? VNDetectedObjectObservation else { break }
        let box = next.boundingBox
        samples.append(Sample(timestampSeconds: frame.timestampSeconds, framePath: frame.path, box: Box(x: box.minX, y: box.minY, width: box.width, height: box.height), confidence: next.confidence, status: next.confidence > 0 ? "tracked" : "lost"))
        observation = next
        if next.confidence <= 0 { break }
    }
    let encoder = JSONEncoder(); encoder.outputFormatting = [.prettyPrinted, .sortedKeys, .withoutEscapingSlashes]
    try encoder.encode(Result(samples: samples)).write(to: URL(fileURLWithPath: CommandLine.arguments[3]), options: .atomic)
} catch { fputs("error: \(error)\n", stderr); exit(2) }
