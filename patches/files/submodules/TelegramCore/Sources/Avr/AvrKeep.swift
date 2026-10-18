import Foundation
import Postbox

/// Messages that other people deleted. With "keep deleted messages" on, the delete update does not remove the message:
/// it stays in the chat and gets a mark in front of its text.
public enum AvrDeleted {
    public static let marker = "🗑 "

    public static func keep(transaction: Transaction, ids: [MessageId]) {
        let shift = marker.utf16.count
        for id in ids {
            transaction.updateMessage(id, update: { currentMessage in
                if currentMessage.text.hasPrefix(marker) {
                    return .skip
                }
                var attributes = currentMessage.attributes
                for (index, attribute) in attributes.enumerated() {
                    if let textEntities = attribute as? TextEntitiesMessageAttribute {
                        let moved = textEntities.entities.map { entity -> MessageTextEntity in
                            return MessageTextEntity(range: (entity.range.lowerBound + shift) ..< (entity.range.upperBound + shift), type: entity.type)
                        }
                        attributes[index] = TextEntitiesMessageAttribute(entities: moved)
                    }
                }
                return .update(StoreMessage(
                    id: currentMessage.id,
                    customStableId: nil,
                    globallyUniqueId: currentMessage.globallyUniqueId,
                    groupingKey: currentMessage.groupingKey,
                    threadId: currentMessage.threadId,
                    timestamp: currentMessage.timestamp,
                    flags: StoreMessageFlags(currentMessage.flags),
                    tags: currentMessage.tags,
                    globalTags: currentMessage.globalTags,
                    localTags: currentMessage.localTags,
                    forwardInfo: currentMessage.forwardInfo.flatMap(StoreMessageForwardInfo.init),
                    authorId: currentMessage.author?.id,
                    text: marker + currentMessage.text,
                    attributes: attributes,
                    media: currentMessage.media
                ))
            })
        }
    }
}

/// The earlier texts of edited messages, kept in the user defaults (up to 30 per message).
public enum AvrEdits {
    private static let storeKey = "avr.edits.v1"
    private static let lock = NSLock()

    private static func key(_ id: MessageId) -> String {
        return "\(id.peerId.toInt64()):\(id.namespace):\(id.id)"
    }

    private static func load() -> [String: [[String: Any]]] {
        return (UserDefaults.standard.dictionary(forKey: storeKey) as? [String: [[String: Any]]]) ?? [:]
    }

    /// Called just before an edit is applied: the text the message had until now is kept.
    public static func record(id: MessageId, previousText: String, previousDate: Int32, newText: String) {
        if !AvrConfig.keepEdits || previousText.isEmpty || previousText == newText {
            return
        }
        lock.lock()
        defer {
            lock.unlock()
        }
        var all = load()
        let name = key(id)
        var list = all[name] ?? []
        if let last = list.last, (last["t"] as? String) == previousText {
            return
        }
        list.append(["d": Int(previousDate), "t": previousText])
        if list.count > 30 {
            list.removeFirst(list.count - 30)
        }
        all[name] = list
        if all.count > 3000 {
            for staleKey in all.keys.prefix(500) where staleKey != name {
                all.removeValue(forKey: staleKey)
            }
        }
        UserDefaults.standard.set(all, forKey: storeKey)
    }

    public static func history(id: MessageId) -> [(Int32, String)] {
        lock.lock()
        defer {
            lock.unlock()
        }
        let list = load()[key(id)] ?? []
        var result: [(Int32, String)] = []
        for item in list {
            if let text = item["t"] as? String, let date = item["d"] as? Int {
                result.append((Int32(truncatingIfNeeded: date), text))
            }
        }
        return result
    }

    /// The versions as one text, the oldest first.
    public static func text(id: MessageId) -> String {
        let formatter = DateFormatter()
        formatter.dateStyle = .short
        formatter.timeStyle = .short
        var parts: [String] = []
        for (date, text) in history(id: id) {
            parts.append(formatter.string(from: Date(timeIntervalSince1970: Double(date))) + "\n" + text)
        }
        return parts.joined(separator: "\n\n")
    }
}
