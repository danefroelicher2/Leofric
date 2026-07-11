import UserNotifications

/// Downloads the event snapshot referenced by `snapshot_id` and attaches it,
/// turning the text push into a rich notification with the photo. Reads the
/// Mac's base URL from the shared App Group (written by the main app's
/// AppSettings). Falls back to the plain text notification on any failure.
final class NotificationService: UNNotificationServiceExtension {
    private var contentHandler: ((UNNotificationContent) -> Void)?
    private var bestAttempt: UNMutableNotificationContent?

    override func didReceive(_ request: UNNotificationRequest,
                             withContentHandler contentHandler: @escaping (UNNotificationContent) -> Void) {
        self.contentHandler = contentHandler
        let content = (request.content.mutableCopy() as? UNMutableNotificationContent)
        bestAttempt = content
        guard let content,
              let snapshotID = request.content.userInfo["snapshot_id"] as? String,
              let baseString = UserDefaults(suiteName: "group.com.danefroelicher.Leofric")?
                  .string(forKey: "leofric.baseURLString"),
              let base = URL(string: baseString)
        else { contentHandler(bestAttempt ?? request.content); return }

        let url = base.appendingPathComponent("snapshot").appendingPathComponent(snapshotID)
        let task = URLSession.shared.downloadTask(with: url) { tempURL, _, _ in
            defer { contentHandler(content) }
            guard let tempURL else { return }
            let dest = FileManager.default.temporaryDirectory
                .appendingPathComponent(snapshotID + ".jpg")
            try? FileManager.default.moveItem(at: tempURL, to: dest)
            if let attachment = try? UNNotificationAttachment(identifier: snapshotID, url: dest) {
                content.attachments = [attachment]
            }
        }
        task.resume()
    }

    override func serviceExtensionTimeWillExpire() {
        if let handler = contentHandler, let content = bestAttempt {
            handler(content)
        }
    }
}
