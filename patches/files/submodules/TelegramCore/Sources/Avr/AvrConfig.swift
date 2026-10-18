import Foundation

/// avrgram's own switches, kept in the app's user defaults under the prefix "avr.".
/// The names follow the Android avrgram so that a setting means the same on both.
public enum AvrConfig {
    private static let prefix = "avr."

    public static func bool(_ key: String, _ fallback: Bool) -> Bool {
        let name = prefix + key
        if UserDefaults.standard.object(forKey: name) == nil {
            return fallback
        }
        return UserDefaults.standard.bool(forKey: name)
    }

    public static func setBool(_ key: String, _ value: Bool) {
        UserDefaults.standard.set(value, forKey: prefix + key)
    }

    public static func int(_ key: String, _ fallback: Int) -> Int {
        let name = prefix + key
        if UserDefaults.standard.object(forKey: name) == nil {
            return fallback
        }
        return UserDefaults.standard.integer(forKey: name)
    }

    public static func setInt(_ key: String, _ value: Int) {
        UserDefaults.standard.set(value, forKey: prefix + key)
    }

    public static func string(_ key: String, _ fallback: String = "") -> String {
        return UserDefaults.standard.string(forKey: prefix + key) ?? fallback
    }

    public static func setString(_ key: String, _ value: String) {
        UserDefaults.standard.set(value, forKey: prefix + key)
    }

    /// Russian or English text, by the language of the phone.
    public static func t(_ ru: String, _ en: String) -> String {
        let language = Locale.preferredLanguages.first ?? "en"
        return language.hasPrefix("ru") ? ru : en
    }

    // ghost mode: what the other side is not told
    public static var ghostRead: Bool { return bool("ghost_read", false) }
    public static var ghostTyping: Bool { return bool("ghost_typing", false) }
    public static var ghostOnline: Bool { return bool("ghost_online", false) }
    public static var ghostStories: Bool { return bool("ghost_stories", false) }
}
