import XCTest
@testable import LeofricApp

final class AppSettingsTests: XCTestCase {
    private func freshDefaults() -> UserDefaults {
        let suiteName = "AppSettingsTests.\(UUID().uuidString)"
        return UserDefaults(suiteName: suiteName)!
    }

    func testDefaultsToMacHostname() {
        let settings = AppSettings(defaults: freshDefaults())
        XCTAssertEqual(settings.baseURLString, "http://Danes-Mac-mini-3.local:5000")
        XCTAssertEqual(settings.baseURL?.host, "Danes-Mac-mini-3.local")
    }

    func testPersistsChangesAcrossInstances() {
        let defaults = freshDefaults()
        let first = AppSettings(defaults: defaults)
        first.baseURLString = "http://192.168.1.50:5000"

        let second = AppSettings(defaults: defaults)
        XCTAssertEqual(second.baseURLString, "http://192.168.1.50:5000")
    }
}
