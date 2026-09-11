import AVFoundation
import Foundation
import Vision

private let usage = """
Usage: track_body_pose VIDEO [--start SECONDS] [--end SECONDS] [--interval SECONDS] [--output PATH]

Detect human body poses at a bounded set of video timestamps. Joint x/y values use
Vision's normalized lower-left coordinate space. JSON is written to stdout unless
--output is supplied.
"""

private enum CLIError: Error, CustomStringConvertible {
    case message(String)

    var description: String {
        switch self {
        case .message(let text): return text
        }
    }
}

private struct Options {
    var videoPath: String
    var startSeconds = 0.0
    var endSeconds: Double?
    var intervalSeconds = 0.1
    var outputPath: String?
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
    let poses: [Pose]

    enum CodingKeys: String, CodingKey {
        case timestampSeconds = "timestamp_seconds"
        case poses
    }
}

private struct Result: Codable {
    let schemaVersion: Int
    let coordinateSpace: String
    let videoPath: String
    let startSeconds: Double
    let endSeconds: Double
    let intervalSeconds: Double
    let samples: [Sample]

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case coordinateSpace = "coordinate_space"
        case videoPath = "video_path"
        case startSeconds = "start_seconds"
        case endSeconds = "end_seconds"
        case intervalSeconds = "interval_seconds"
        case samples
    }
}

private func parseDouble(_ text: String, flag: String) throws -> Double {
    guard let value = Double(text), value.isFinite else {
        throw CLIError.message("Invalid value for \(flag): \(text)")
    }
    return value
}

private func parseOptions(_ arguments: [String]) throws -> Options? {
    if arguments.contains("--help") || arguments.contains("-h") {
        print(usage)
        return nil
    }
    guard let videoPath = arguments.first, !videoPath.hasPrefix("-") else {
        throw CLIError.message(usage)
    }
    var options = Options(videoPath: videoPath)
    var index = 1
    while index < arguments.count {
        let flag = arguments[index]
        guard index + 1 < arguments.count else {
            throw CLIError.message("Missing value for \(flag)")
        }
        let value = arguments[index + 1]
        switch flag {
        case "--start": options.startSeconds = try parseDouble(value, flag: flag)
        case "--end": options.endSeconds = try parseDouble(value, flag: flag)
        case "--interval": options.intervalSeconds = try parseDouble(value, flag: flag)
        case "--output": options.outputPath = value
        default: throw CLIError.message("Unknown option: \(flag)\n\(usage)")
        }
        index += 2
    }
    guard options.startSeconds >= 0 else {
        throw CLIError.message("--start must be greater than or equal to zero")
    }
    guard options.intervalSeconds > 0 else {
        throw CLIError.message("--interval must be greater than zero")
    }
    if let end = options.endSeconds, end < options.startSeconds {
        throw CLIError.message("--end must be greater than or equal to --start")
    }
    return options
}

private func sampleTimes(start: Double, end: Double, interval: Double) -> [Double] {
    guard end >= start else { return [] }
    var values: [Double] = []
    var index = 0
    while true {
        let value = start + Double(index) * interval
        if value > end + 1e-9 { break }
        values.append(min(value, end))
        index += 1
    }
    return values
}

private func detectPoses(in image: CGImage) throws -> [Pose] {
    let request = VNDetectHumanBodyPoseRequest()
    let handler = VNImageRequestHandler(cgImage: image, orientation: .up)
    try handler.perform([request])
    return try (request.results ?? []).map { observation in
        let points = try observation.recognizedPoints(.all)
        let joints = points.map { name, point in
            Joint(
                name: name.rawValue.rawValue,
                x: Double(point.location.x),
                y: Double(point.location.y),
                confidence: point.confidence
            )
        }.sorted { $0.name < $1.name }
        let confidence = joints.map(\.confidence).max() ?? 0
        return Pose(confidence: confidence, joints: joints)
    }
}

private func writeJSON<T: Encodable>(_ value: T, outputPath: String?) throws {
    let encoder = JSONEncoder()
    encoder.outputFormatting = [.prettyPrinted, .sortedKeys, .withoutEscapingSlashes]
    let data = try encoder.encode(value)
    if let path = outputPath {
        try data.write(to: URL(fileURLWithPath: path), options: .atomic)
    } else {
        FileHandle.standardOutput.write(data)
        FileHandle.standardOutput.write(Data("\n".utf8))
    }
}

private func run(_ options: Options) throws {
    let videoURL = URL(fileURLWithPath: options.videoPath)
    guard FileManager.default.fileExists(atPath: videoURL.path) else {
        throw CLIError.message("Video does not exist: \(options.videoPath)")
    }
    let asset = AVURLAsset(url: videoURL)
    let duration = CMTimeGetSeconds(asset.duration)
    guard duration.isFinite, duration >= 0 else {
        throw CLIError.message("Could not determine video duration")
    }
    let end = min(options.endSeconds ?? duration, duration)
    guard options.startSeconds <= duration, end >= options.startSeconds else {
        throw CLIError.message("Requested range is outside the video duration (\(duration) seconds)")
    }

    let generator = AVAssetImageGenerator(asset: asset)
    generator.appliesPreferredTrackTransform = true
    generator.requestedTimeToleranceBefore = .zero
    generator.requestedTimeToleranceAfter = .zero

    var samples: [Sample] = []
    for seconds in sampleTimes(start: options.startSeconds, end: end, interval: options.intervalSeconds) {
        var actual = CMTime.zero
        let image = try generator.copyCGImage(
            at: CMTime(seconds: seconds, preferredTimescale: 600),
            actualTime: &actual
        )
        let timestamp = CMTimeGetSeconds(actual)
        samples.append(Sample(timestampSeconds: timestamp.isFinite ? timestamp : seconds, poses: try detectPoses(in: image)))
    }

    try writeJSON(Result(
        schemaVersion: 1,
        coordinateSpace: "vision_normalized_lower_left",
        videoPath: videoURL.path,
        startSeconds: options.startSeconds,
        endSeconds: end,
        intervalSeconds: options.intervalSeconds,
        samples: samples
    ), outputPath: options.outputPath)
}

do {
    if let options = try parseOptions(Array(CommandLine.arguments.dropFirst())) {
        try run(options)
    }
} catch {
    FileHandle.standardError.write(Data("error: \(error)\n".utf8))
    exit(2)
}
