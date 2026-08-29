import Foundation
import ImageIO
import Vision

private struct FrameInput: Decodable {
    let path: String
    let timestampSeconds: Double
    enum CodingKeys: String, CodingKey {
        case path
        case timestampSeconds = "timestamp_seconds"
    }
}

private struct Joint: Codable {
    let name: String
    let x: Double
    let y: Double
    let confidence: Float
}

private struct Pose: Codable {
    let confidence: Float
    let joints: [Joint]
}

private struct Sample: Codable {
    let timestampSeconds: Double
    let framePath: String
    let poses: [Pose]
    enum CodingKeys: String, CodingKey {
        case timestampSeconds = "timestamp_seconds"
        case framePath = "frame_path"
        case poses
    }
}

private struct Result: Codable {
    let schemaVersion = 1
    let coordinateSpace = "vision_normalized_lower_left"
    let inference = "VNDetectHumanBodyPoseRequest"
    let samples: [Sample]
    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case coordinateSpace = "coordinate_space"
        case inference
        case samples
    }
}

guard CommandLine.arguments.count == 3 else {
    fputs("Usage: analyze_body_pose_frames INPUT.json OUTPUT.json\n", stderr)
    exit(2)
}

do {
    let inputURL = URL(fileURLWithPath: CommandLine.arguments[1])
    let frames = try JSONDecoder().decode([FrameInput].self, from: Data(contentsOf: inputURL))
    var samples: [Sample] = []
    for frame in frames {
        let url = URL(fileURLWithPath: frame.path) as CFURL
        guard let source = CGImageSourceCreateWithURL(url, nil),
              let image = CGImageSourceCreateImageAtIndex(source, 0, nil) else {
            throw NSError(domain: "SceneFactory", code: 1, userInfo: [NSLocalizedDescriptionKey: "Cannot read \(frame.path)"])
        }
        let request = VNDetectHumanBodyPoseRequest()
        request.usesCPUOnly = true
        try VNImageRequestHandler(cgImage: image, orientation: .up).perform([request])
        let poses = try (request.results ?? []).map { observation in
            let joints = try observation.recognizedPoints(.all).map { name, point in
                Joint(name: name.rawValue.rawValue, x: Double(point.location.x), y: Double(point.location.y), confidence: point.confidence)
            }.sorted { $0.name < $1.name }
            return Pose(confidence: joints.map(\.confidence).max() ?? 0, joints: joints)
        }
        samples.append(Sample(timestampSeconds: frame.timestampSeconds, framePath: frame.path, poses: poses))
    }
    let encoder = JSONEncoder()
    encoder.outputFormatting = [.prettyPrinted, .sortedKeys, .withoutEscapingSlashes]
    try encoder.encode(Result(samples: samples)).write(to: URL(fileURLWithPath: CommandLine.arguments[2]), options: .atomic)
} catch {
    fputs("error: \(error)\n", stderr)
    exit(2)
}
