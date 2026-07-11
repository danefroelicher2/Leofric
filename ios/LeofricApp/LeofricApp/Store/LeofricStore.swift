import Combine
import Foundation

/// Owns the single LeofricAPI instance every tab shares, rebuilt whenever
/// the user changes the Mac's address in Settings. Fixes a Phase 2C review
/// finding: LiveFeedView and NodesView each built their own LeofricAPI,
/// which would have quadrupled once Alerts and Chats needed one too.
final class LeofricStore: ObservableObject {
    @Published private(set) var api: LeofricAPI

    private var cancellable: AnyCancellable?

    init(settings: AppSettings) {
        api = Self.makeAPI(from: settings)
        cancellable = settings.$baseURLString
            .sink { [weak self] _ in
                guard let self else { return }
                self.api = Self.makeAPI(from: settings)
            }
    }

    private static func makeAPI(from settings: AppSettings) -> LeofricAPI {
        LeofricAPI(baseURL: settings.baseURL ?? URL(string: "http://invalid.local:0")!)
    }
}
