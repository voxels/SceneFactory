import Foundation
import ImageIO
import Vision

private struct Input: Decodable {
    let assetID: String
    let path: String
    enum CodingKeys: String, CodingKey { case assetID = "asset_id"; case path }
}

private struct Point: Codable {
    let x: Double
    let y: Double
    let confidence: Float
}

private struct Region: Codable {
    let name: String
    let points: [Point]
}

private struct Box: Codable {
    let x: Double
    let y: Double
    let width: Double
    let height: Double
}

private struct Face: Codable {
    let confidence: Float
    let box: Box
    let landmarks: [Region]
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

private struct Record: Codable {
    let assetID: String
    let path: String
    let width: Int
    let height: Int
    let faces: [Face]
    let bodyPoses: [Pose]
    enum CodingKeys: String, CodingKey {
        case assetID = "asset_id"; case path; case width; case height
        case faces; case bodyPoses = "body_poses"
    }
}

private struct Result: Codable {
    let schemaVersion = 4
    let coordinateSpace = "vision_normalized_lower_left"
    let faceDetector = "VNDetectFaceLandmarksRequest"
    let bodyDetector = "VNDetectHumanBodyPoseRequest"
    let records: [Record]
    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"; case coordinateSpace = "coordinate_space"
        case faceDetector = "face_detector"; case bodyDetector = "body_detector"; case records
    }
}

private func points(_ region: VNFaceLandmarkRegion2D?) -> [Point] {
    guard let region else { return [] }
    return region.normalizedPoints.map { Point(x: Double($0.x), y: Double($0.y), confidence: 1.0) }
}

private func regions(_ landmarks: VNFaceLandmarks2D?) -> [Region] {
    guard let landmarks else { return [] }
    return [
        Region(name: "face_contour", points: points(landmarks.faceContour)),
        Region(name: "left_eye", points: points(landmarks.leftEye)),
        Region(name: "right_eye", points: points(landmarks.rightEye)),
        Region(name: "left_eyebrow", points: points(landmarks.leftEyebrow)),
        Region(name: "right_eyebrow", points: points(landmarks.rightEyebrow)),
        Region(name: "nose", points: points(landmarks.nose)),
        Region(name: "nose_crest", points: points(landmarks.noseCrest)),
        Region(name: "outer_lips", points: points(landmarks.outerLips)),
        Region(name: "inner_lips", points: points(landmarks.innerLips)),
        Region(name: "left_pupil", points: points(landmarks.leftPupil)),
        Region(name: "right_pupil", points: points(landmarks.rightPupil)),
    ].filter { !$0.points.isEmpty }
}

guard CommandLine.arguments.count == 3 else {
    fputs("Usage: analyze_visual_frames INPUT.json OUTPUT.json\n", stderr)
    exit(2)
}

do {
    let inputs = try JSONDecoder().decode([Input].self, from: Data(contentsOf: URL(fileURLWithPath: CommandLine.arguments[1])))
    var records: [Record] = []
    for input in inputs {
        guard let source = CGImageSourceCreateWithURL(URL(fileURLWithPath: input.path) as CFURL, nil),
              let image = CGImageSourceCreateImageAtIndex(source, 0, nil) else {
            throw NSError(domain: "SceneFactory", code: 1, userInfo: [NSLocalizedDescriptionKey: "Cannot read \(input.path)"])
        }
        let faceRequest = VNDetectFaceLandmarksRequest()
        faceRequest.usesCPUOnly = true
        let poseRequest = VNDetectHumanBodyPoseRequest()
        poseRequest.usesCPUOnly = true
        try VNImageRequestHandler(cgImage: image, orientation: .up).perform([faceRequest, poseRequest])
        let faces = (faceRequest.results ?? []).map { observation in
            Face(
                confidence: observation.confidence,
                box: Box(x: Double(observation.boundingBox.minX), y: Double(observation.boundingBox.minY), width: Double(observation.boundingBox.width), height: Double(observation.boundingBox.height)),
                landmarks: regions(observation.landmarks)
            )
        }
        let poses = try (poseRequest.results ?? []).map { observation in
            let joints = try observation.recognizedPoints(.all).map { name, point in
                Joint(name: name.rawValue.rawValue, x: Double(point.location.x), y: Double(point.location.y), confidence: point.confidence)
            }.sorted { $0.name < $1.name }
            return Pose(confidence: joints.map(\.confidence).max() ?? 0, joints: joints)
        }
        records.append(Record(assetID: input.assetID, path: input.path, width: image.width, height: image.height, faces: faces, bodyPoses: poses))
    }
    let encoder = JSONEncoder()
    encoder.outputFormatting = [.prettyPrinted, .sortedKeys, .withoutEscapingSlashes]
    try encoder.encode(Result(records: records)).write(to: URL(fileURLWithPath: CommandLine.arguments[2]), options: .atomic)
} catch {
    fputs("error: \(error)\n", stderr)
    exit(2)
}
