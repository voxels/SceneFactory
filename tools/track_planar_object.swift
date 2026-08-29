import AVFoundation
import Foundation
import Vision

private let usage = """
Usage: track_planar_object VIDEO --bbox X,Y,WIDTH,HEIGHT [--start SECONDS] [--end SECONDS] [--interval SECONDS] [--output PATH]

Track one rigid object from a caller-supplied initial bounding box. Box values must
be normalized to Vision's lower-left coordinate space. JSON is written to stdout
unless --output is supplied.
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
    var boundingBox: CGRect?
    var startSeconds = 0.0
    var endSeconds: Double?
    var intervalSeconds = 0.1
    var outputPath: String?
}

private struct Box: Codable {
    let x: Double
    let y: Double
    let width: Double
    let height: Double

    init(_ rect: CGRect) {
        x = Double(rect.origin.x)
        y = Double(rect.origin.y)
        width = Double(rect.width)
        height = Double(rect.height)
    }
}

private struct Sample: Codable {
    let timestampSeconds: Double
    let box: Box
    let confidence: Float
    let status: String

    enum CodingKeys: String, CodingKey {
        case timestampSeconds = "timestamp_seconds"
        case box
        case confidence
        case status
    }
}

private struct Result: Codable {
    let schemaVersion: Int
    let coordinateSpace: String
    let videoPath: String
    let startSeconds: Double
    let endSeconds: Double
    let intervalSeconds: Double
    let initialization: String
    let samples: [Sample]

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case coordinateSpace = "coordinate_space"
        case videoPath = "video_path"
        case startSeconds = "start_seconds"
        case endSeconds = "end_seconds"
        case intervalSeconds = "interval_seconds"
        case initialization
        case samples
    }
}

private func parseDouble(_ text: String, flag: String) throws -> Double {
    guard let value = Double(text), value.isFinite else {
        throw CLIError.message("Invalid value for \(flag): \(text)")
    }
    return value
}

private func parseBox(_ text: String) throws -> CGRect {
    let values = text.split(separator: ",", omittingEmptySubsequences: false)
    guard values.count == 4 else {
        throw CLIError.message("--bbox must contain X,Y,WIDTH,HEIGHT")
    }
    let numbers = try values.map { try parseDouble(String($0), flag: "--bbox") }
    let rect = CGRect(x: numbers[0], y: numbers[1], width: numbers[2], height: numbers[3])
    guard rect.minX >= 0, rect.minY >= 0, rect.width > 0, rect.height > 0,
          rect.maxX <= 1, rect.maxY <= 1 else {
        throw CLIError.message("--bbox must be a non-empty normalized box fully inside 0...1")
    }
    return rect
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
        case "--bbox": options.boundingBox = try parseBox(value)
        case "--start": options.startSeconds = try parseDouble(value, flag: flag)
        case "--end": options.endSeconds = try parseDouble(value, flag: flag)
        case "--interval": options.intervalSeconds = try parseDouble(value, flag: flag)
        case "--output": options.outputPath = value
        default: throw CLIError.message("Unknown option: \(flag)\n\(usage)")
        }
        index += 2
    }
    guard options.boundingBox != nil else {
        throw CLIError.message("Missing required --bbox X,Y,WIDTH,HEIGHT")
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

    let times = sampleTimes(start: options.startSeconds, end: end, interval: options.intervalSeconds)
    guard let firstTime = times.first, let initialBox = options.boundingBox else {
        throw CLIError.message("The requested range produced no samples")
    }

    var actual = CMTime.zero
    _ = try generator.copyCGImage(
        at: CMTime(seconds: firstTime, preferredTimescale: 600),
        actualTime: &actual
    )
    let initialTimestamp = CMTimeGetSeconds(actual)
    var samples = [Sample(
        timestampSeconds: initialTimestamp.isFinite ? initialTimestamp : firstTime,
        box: Box(initialBox),
        confidence: 1,
        status: "initialized"
    )]
    var previous = VNDetectedObjectObservation(boundingBox: initialBox)
    let sequenceHandler = VNSequenceRequestHandler()

    for seconds in times.dropFirst() {
        var frameTime = CMTime.zero
        let image = try generator.copyCGImage(
            at: CMTime(seconds: seconds, preferredTimescale: 600),
            actualTime: &frameTime
        )
        let request = VNTrackObjectRequest(detectedObjectObservation: previous)
        request.trackingLevel = .accurate
        try sequenceHandler.perform([request], on: image, orientation: .up)
        guard let observation = request.results?.first as? VNDetectedObjectObservation else {
            break
        }
        let timestamp = CMTimeGetSeconds(frameTime)
        samples.append(Sample(
            timestampSeconds: timestamp.isFinite ? timestamp : seconds,
            box: Box(observation.boundingBox),
            confidence: observation.confidence,
            status: observation.confidence > 0 ? "tracked" : "lost"
        ))
        previous = observation
        if request.isLastFrame || observation.confidence <= 0 { break }
    }

    try writeJSON(Result(
        schemaVersion: 1,
        coordinateSpace: "vision_normalized_lower_left",
        videoPath: videoURL.path,
        startSeconds: options.startSeconds,
        endSeconds: end,
        intervalSeconds: options.intervalSeconds,
        initialization: "caller_supplied_bbox",
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
