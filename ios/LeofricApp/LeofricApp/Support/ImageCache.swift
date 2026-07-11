import UIKit

/// A small in-memory image cache for Alerts thumbnails and the full-photo
/// view, so scrolling a list doesn't refetch the same snapshot repeatedly.
/// NSCache-backed rather than a third-party library, per the zero-dependency
/// constraint — this is the whole feature, nothing more is needed at this
/// app's scale.
@MainActor
final class ImageCache: ObservableObject {
    static let shared = ImageCache()

    private let cache = NSCache<NSURL, UIImage>()

    func image(for url: URL, session: URLSession = .shared) async -> UIImage? {
        if let cached = cache.object(forKey: url as NSURL) {
            return cached
        }
        guard let (data, response) = try? await session.data(from: url),
              let http = response as? HTTPURLResponse, http.statusCode == 200,
              let image = UIImage(data: data)
        else {
            return nil
        }
        cache.setObject(image, forKey: url as NSURL)
        return image
    }
}
