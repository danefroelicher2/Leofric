import SwiftUI

/// Full-size photo for one alert, with a way back to the live feed for that
/// node. There is no in-app tab-programmatic-navigation primitive wired up
/// yet (RootTabView's `selection` is private) — "Watch Live" is a dismiss +
/// instruction rather than an automatic tab jump, matching the simplest
/// correct behavior for this phase; wiring a shared tab-selection binding is
/// a cheap follow-up if this proves annoying in daily use.
struct AlertDetailView: View {
    let event: LeofricEvent
    @EnvironmentObject private var store: LeofricStore
    @Environment(\.dismiss) private var dismiss
    @State private var image: UIImage?

    var body: some View {
        VStack(spacing: 16) {
            if let image {
                Image(uiImage: image)
                    .resizable()
                    .aspectRatio(contentMode: .fit)
            } else {
                ProgressView()
                    .frame(maxWidth: .infinity, minHeight: 200)
            }

            VStack(alignment: .leading, spacing: 4) {
                Text(event.eventType.capitalized)
                    .font(.headline)
                if let name = event.metadata.name {
                    Text(name == "unknown" ? "Unknown person" : name.capitalized)
                        .foregroundStyle(name == "unknown" ? .red : .primary)
                }
                Text(event.nodeID)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            .frame(maxWidth: .infinity, alignment: .leading)

            Button("Watch Live") { dismiss() }
                .buttonStyle(.borderedProminent)

            Spacer()
        }
        .padding()
        .navigationTitle("Alert")
        .task { await loadImage() }
    }

    private func loadImage() async {
        guard let snapshotID = event.metadata.snapshotID else { return }
        image = await ImageCache.shared.image(for: store.api.snapshotURL(id: snapshotID))
    }
}
