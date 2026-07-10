import Foundation

/// Persists the one setting this phase needs: the Mac's address. At home
/// that's the mDNS hostname; Phase 2E adds Tailscale as an alternative
/// address the user can type here — the field itself doesn't change.
final class AppSettings: ObservableObject {
    private enum Keys {
        static let baseURLString = "leofric.baseURLString"
    }

    static let defaultBaseURLString = "http://Danes-Mac-mini-3.local:5000"

    private let defaults: UserDefaults

    @Published var baseURLString: String {
        didSet { defaults.set(baseURLString, forKey: Keys.baseURLString) }
    }

    init(defaults: UserDefaults = .standard) {
        self.defaults = defaults
        self.baseURLString = defaults.string(forKey: Keys.baseURLString) ?? Self.defaultBaseURLString
    }

    var baseURL: URL? {
        URL(string: baseURLString)
    }
}
