import UserNotifications

/// Downloads the event snapshot referenced by `snapshot_id` and attaches it,
/// turning the text push into a rich notification with the photo. Reads the
/// Mac's base URL from the shared App Group (written by the main app's
/// AppSettings). Falls back to the plain text notification on any failure.
final class NotificationService: UNNotificationServiceExtension {
    private var contentHandler: ((UNNotificationContent) -> Void)?
    private var bestAttempt: UNMutableNotificationContent?
    private var downloadTask: URLSessionDownloadTask?
    private let lock = NSLock()

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
        else { deliver(bestAttempt ?? request.content); return }

        let url = base.appendingPathComponent("snapshot").appendingPathComponent(snapshotID)
        downloadTask = URLSession.shared.downloadTask(with: url) { [weak self] tempURL, _, _ in
            defer { self?.deliver(content) }
            guard let tempURL else { return }
            let dest = FileManager.default.temporaryDirectory
                .appendingPathComponent(snapshotID + ".jpg")
            try? FileManager.default.moveItem(at: tempURL, to: dest)
            if let attachment = try? UNNotificationAttachment(identifier: snapshotID, url: dest) {
                content.attachments = [attachment]
            }
        }
        downloadTask?.resume()
    }

    override func serviceExtensionTimeWillExpire() {
        // iOS is about to kill the extension: cancel the in-flight download and
        // deliver whatever we have. deliver() is idempotent, so if the download
        // finishes at the same moment, the handler still fires exactly once.
        downloadTask?.cancel()
        deliver(bestAttempt)
    }

    /// Calls the content handler at most once — whichever of the download
    /// completion or the timeout fires first wins; later calls are no-ops.
    /// Calling a notification-extension handler twice is undefined behavior,
    /// and the download-past-timeout race is real over slow links (Tailscale).
    private func deliver(_ content: UNNotificationContent?) {
        lock.lock()
        let handler = contentHandler
        contentHandler = nil
        lock.unlock()
        guard let handler, let content else { return }
        handler(content)
    }
}
