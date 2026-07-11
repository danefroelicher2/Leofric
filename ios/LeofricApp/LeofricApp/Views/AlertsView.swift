import SwiftUI

/// The security timeline: every motion/person/identity event, newest first,
/// with a thumbnail when one exists (person/identity only — motion has no
/// snapshot_id, per the Mac's design). Filter by event type via a menu.
struct AlertsView: View {
    @EnvironmentObject private var store: LeofricStore
    @State private var events: [LeofricEvent] = []
    @State private var filter: String? = nil  // nil = all types
    @State private var isLoading = false

    private let filterOptions: [(label: String, value: String?)] = [
        ("All", nil), ("Motion", "motion"), ("Person", "person"), ("Identity", "identity"),
    ]

    var body: some View {
        NavigationStack {
            List(events) { event in
                NavigationLink(value: event) {
                    AlertRow(event: event)
                }
            }
            .navigationDestination(for: LeofricEvent.self) { event in
                AlertDetailView(event: event)
            }
            .navigationTitle("Alerts")
            .toolbar {
                Menu {
                    ForEach(filterOptions, id: \.label) { option in
                        Button(option.label) {
                            filter = option.value
                            Task { await refresh() }
                        }
                    }
                } label: {
                    Image(systemName: "line.3.horizontal.decrease.circle")
                }
            }
            .refreshable { await refresh() }
            .task { await refresh() }
            .overlay {
                if events.isEmpty && !isLoading {
                    ContentUnavailableView("No Alerts Yet", systemImage: "bell.slash")
                }
            }
        }
    }

    private func refresh() async {
        isLoading = true
        defer { isLoading = false }
        events = (try? await store.api.fetchEvents(eventType: filter)) ?? events
    }
}

private struct AlertRow: View {
    let event: LeofricEvent
    @EnvironmentObject private var store: LeofricStore
    @State private var thumbnail: UIImage?

    var body: some View {
        HStack(spacing: 12) {
            Group {
                if let thumbnail {
                    Image(uiImage: thumbnail).resizable().aspectRatio(contentMode: .fill)
                } else {
                    Image(systemName: iconName)
                        .foregroundStyle(.secondary)
                }
            }
            .frame(width: 56, height: 56)
            .clipShape(RoundedRectangle(cornerRadius: 8))
            .background(Color.secondary.opacity(0.1), in: RoundedRectangle(cornerRadius: 8))

            VStack(alignment: .leading, spacing: 2) {
                Text(title)
                    .font(.subheadline).bold()
                if let date = event.createdAtDate {
                    Text(date, style: .relative)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
            Spacer()
        }
        .task { await loadThumbnail() }
    }

    private var title: String {
        switch event.eventType {
        case "identity":
            let name = event.metadata.name ?? "unknown"
            return name == "unknown" ? "Unknown person" : name.capitalized
        case "person": return "Person detected"
        case "motion": return "Motion"
        default: return event.eventType.capitalized
        }
    }

    private var iconName: String {
        switch event.eventType {
        case "identity": return "person.crop.circle"
        case "person": return "figure.walk"
        default: return "sensor.tag.radiowaves.forward"
        }
    }

    private func loadThumbnail() async {
        guard let snapshotID = event.metadata.snapshotID else { return }
        thumbnail = await ImageCache.shared.image(for: store.api.snapshotURL(id: snapshotID))
    }
}

extension LeofricEvent: Hashable {
    static func == (lhs: LeofricEvent, rhs: LeofricEvent) -> Bool { lhs.id == rhs.id }
    func hash(into hasher: inout Hasher) { hasher.combine(id) }
}
