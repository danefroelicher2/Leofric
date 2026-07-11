import Foundation
import UIKit
import UserNotifications

/// Requests notification permission, registers for remote notifications, and
/// ships the resulting APNs device token to the Mac. The Simulator can't get a
/// real token, so this only does anything meaningful on a physical device.
enum PushRegistrar {
    static func hexString(from token: Data) -> String {
        token.map { String(format: "%02x", $0) }.joined()
    }

    static func requestAndRegister() {
        UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .sound, .badge]) { granted, _ in
            guard granted else { return }
            DispatchQueue.main.async {
                UIApplication.shared.registerForRemoteNotifications()
            }
        }
    }

    static func sendToken(_ token: Data) {
        let hex = hexString(from: token)
        let settings = AppSettings()
        guard let baseURL = settings.baseURL else { return }
        Task { try? await LeofricAPI(baseURL: baseURL).registerDevice(token: hex) }
    }
}

final class AppDelegate: NSObject, UIApplicationDelegate {
    func application(_ application: UIApplication,
                     didFinishLaunchingWithOptions options: [UIApplication.LaunchOptionsKey: Any]? = nil) -> Bool {
        PushRegistrar.requestAndRegister()
        return true
    }

    func application(_ application: UIApplication,
                     didRegisterForRemoteNotificationsWithDeviceToken deviceToken: Data) {
        PushRegistrar.sendToken(deviceToken)
    }

    func application(_ application: UIApplication,
                     didFailToRegisterForRemoteNotificationsWithError error: Error) {
        // Expected on the Simulator; silent on device unless entitlement missing.
    }
}
