import Foundation
import EventKit

/// The AI of avrgram: one small client that talks to the model with the owner's own key.
/// Three formats are understood: OpenAI-compatible (OpenAI, OpenRouter, DeepSeek, Groq, a local server ...),
/// Anthropic and Google Gemini. "Auto" picks one from the key and the address.
public enum AvrAi {
    public static var enabled: Bool {
        return AvrConfig.bool("ai_on", false) && !apiKey().isEmpty
    }

    private static func apiKey() -> String {
        return AvrConfig.string("ai_key").trimmingCharacters(in: .whitespacesAndNewlines)
    }

    private static func format() -> Int {
        let chosen = AvrConfig.int("ai_format", 0)
        if chosen != 0 {
            return chosen
        }
        let key = apiKey()
        let address = AvrConfig.string("ai_url").lowercased()
        if address.contains("anthropic.com") || key.hasPrefix("sk-ant-") {
            return 2
        }
        if address.contains("googleapis.com") || key.hasPrefix("AIza") {
            return 3
        }
        return 1
    }

    private static func model() -> String {
        let chosen = AvrConfig.string("ai_model").trimmingCharacters(in: .whitespacesAndNewlines)
        if !chosen.isEmpty {
            return chosen
        }
        switch format() {
        case 2:
            return "claude-haiku-5-5"
        case 3:
            return "gemini-2.0-flash"
        default:
            return "gpt-4o-mini"
        }
    }

    private static func finish(_ completion: @escaping (String?, String?) -> Void, _ text: String?, _ error: String?) {
        DispatchQueue.main.async {
            completion(text, error)
        }
    }

    /// One request. The completion is called on the main queue with the text or an error.
    public static func complete(system: String, user: String, maxTokens: Int, completion: @escaping (String?, String?) -> Void) {
        let kind = format()
        let key = apiKey()
        let name = model()
        var base = AvrConfig.string("ai_url").trimmingCharacters(in: .whitespacesAndNewlines)
        while base.hasSuffix("/") {
            base.removeLast()
        }
        let address: String
        let body: [String: Any]
        var headers: [String: String] = ["Content-Type": "application/json"]
        switch kind {
        case 2:
            if base.isEmpty {
                base = "https://api.anthropic.com"
            }
            address = base.hasSuffix("/v1") ? base + "/messages" : base + "/v1/messages"
            body = ["model": name, "max_tokens": maxTokens, "system": system, "messages": [["role": "user", "content": user]]]
            headers["x-api-key"] = key
            headers["anthropic-version"] = "2023-06-01"
        case 3:
            if base.isEmpty {
                base = "https://generativelanguage.googleapis.com"
            }
            address = base + "/v1beta/models/" + name + ":generateContent"
            body = [
                "systemInstruction": ["parts": [["text": system]]],
                "contents": [["role": "user", "parts": [["text": user]]]],
                "generationConfig": ["maxOutputTokens": maxTokens]
            ]
            headers["x-goog-api-key"] = key
        default:
            if base.isEmpty {
                base = "https://api.openai.com/v1"
            }
            address = base.hasSuffix("/chat/completions") ? base : base + "/chat/completions"
            body = ["model": name, "max_tokens": maxTokens, "messages": [["role": "system", "content": system], ["role": "user", "content": user]]]
            headers["Authorization"] = "Bearer " + key
        }
        guard let url = URL(string: address), let data = try? JSONSerialization.data(withJSONObject: body) else {
            finish(completion, nil, "bad address")
            return
        }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.timeoutInterval = 60
        request.httpBody = data
        for (field, value) in headers {
            request.setValue(value, forHTTPHeaderField: field)
        }
        URLSession.shared.dataTask(with: request) { responseData, response, error in
            if let error = error {
                finish(completion, nil, error.localizedDescription)
                return
            }
            let status = (response as? HTTPURLResponse)?.statusCode ?? 0
            guard let responseData = responseData, let object = (try? JSONSerialization.jsonObject(with: responseData)) as? [String: Any] else {
                finish(completion, nil, "HTTP \(status)")
                return
            }
            if status >= 400 {
                var message = "HTTP \(status)"
                if let failure = object["error"] as? [String: Any], let text = failure["message"] as? String {
                    message += ": " + text
                } else if let text = object["error"] as? String {
                    message += ": " + text
                }
                finish(completion, nil, String(message.prefix(240)))
                return
            }
            var text = ""
            switch kind {
            case 2:
                if let content = object["content"] as? [[String: Any]] {
                    text = content.compactMap { $0["text"] as? String }.joined()
                }
            case 3:
                if let candidates = object["candidates"] as? [[String: Any]], let first = candidates.first, let content = first["content"] as? [String: Any], let parts = content["parts"] as? [[String: Any]] {
                    text = parts.compactMap { $0["text"] as? String }.joined()
                }
            default:
                if let choices = object["choices"] as? [[String: Any]], let first = choices.first, let message = first["message"] as? [String: Any], let content = message["content"] as? String {
                    text = content
                }
            }
            if text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                finish(completion, nil, "empty answer")
            } else {
                finish(completion, text, nil)
            }
        }.resume()
    }

    /// The first {...} object in an answer of the model.
    public static func json(from answer: String) -> [String: Any]? {
        guard let start = answer.firstIndex(of: "{"), let end = answer.lastIndex(of: "}"), start < end else {
            return nil
        }
        guard let data = String(answer[start ... end]).data(using: .utf8) else {
            return nil
        }
        return (try? JSONSerialization.jsonObject(with: data)) as? [String: Any]
    }

    // MARK: replies

    /// Three answers the owner could send, in the owner's style.
    public static func replyOptions(message: String, completion: @escaping ([String]?, String?) -> Void) {
        var system = "You help the owner of a Telegram account answer a message without writing it. "
            + "Offer 3 different short answers the owner could send, in the language of the message, "
            + "the way a friendly person writes in a chat: natural, short, no formal phrases. "
            + "Never invent facts, times, prices or promises the owner did not state; when an answer needs a fact you do not have, "
            + "make it a short question or a stalling reply. Reply with JSON only: {\"options\":[\"...\",\"...\",\"...\"]}"
        let note = AvrConfig.string("ai_note").trimmingCharacters(in: .whitespacesAndNewlines)
        if !note.isEmpty {
            system += " The owner says about their style: " + note
        }
        complete(system: system, user: "Message:\n" + message, maxTokens: 400, completion: { text, error in
            guard let text = text else {
                completion(nil, error)
                return
            }
            let options = (json(from: text)?["options"] as? [String]) ?? []
            let cleaned = options.map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }.filter { !$0.isEmpty }
            completion(cleaned.isEmpty ? nil : cleaned, cleaned.isEmpty ? "no options" : nil)
        })
    }

    // MARK: plans

    public struct Plan {
        public var title: String
        public var type: String
        public var start: Date
        public var end: Date
        public var allDay: Bool
        public var place: String
    }

    /// Finds a plan (meeting, call, deadline, task ...) in a message. The completion gets nil and an error when there is none.
    public static func plan(message: String, completion: @escaping (Plan?, String?) -> Void) {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.dateFormat = "EEEE yyyy-MM-dd HH:mm"
        let system = "You find a plan in ONE chat message. Now it is " + formatter.string(from: Date()) + " (" + TimeZone.current.identifier + "). "
            + "Reply with JSON only: {\"plan\":true|false,\"type\":\"meeting|call|deadline|task|payment|promise|reminder\","
            + "\"title\":\"short title in the language of the message\",\"start\":\"YYYY-MM-DDTHH:MM or YYYY-MM-DD or empty\","
            + "\"end\":\"same format or empty\",\"all_day\":true|false,\"place\":\"\"}. "
            + "plan=false when there is no concrete plan (small talk, the past, a hypothetical). "
            + "Work out relative dates (tomorrow, on Friday, in two hours) from the time given above. A date without a time is all_day."
        complete(system: system, user: "Message:\n" + message, maxTokens: 300, completion: { text, error in
            guard let text = text else {
                completion(nil, error)
                return
            }
            guard let object = json(from: text), (object["plan"] as? Bool) == true, let title = object["title"] as? String, !title.isEmpty,
                  let startText = object["start"] as? String, let start = parseDate(startText) else {
                completion(nil, AvrConfig.t("В сообщении нет плана с датой", "No plan with a date in the message"))
                return
            }
            let allDay = (object["all_day"] as? Bool) ?? (startText.count < 16)
            let defaultLength: TimeInterval = allDay ? 86400 : 3600
            let end = (object["end"] as? String).flatMap(parseDate) ?? start.addingTimeInterval(defaultLength)
            completion(Plan(title: title, type: (object["type"] as? String) ?? "task", start: start, end: end > start ? end : start.addingTimeInterval(defaultLength), allDay: allDay, place: (object["place"] as? String) ?? ""), nil)
        })
    }

    private static func parseDate(_ value: String) -> Date? {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.timeZone = TimeZone.current
        if value.count >= 16 {
            formatter.dateFormat = "yyyy-MM-dd'T'HH:mm"
            return formatter.date(from: String(value.prefix(16)))
        }
        if value.count >= 10 {
            formatter.dateFormat = "yyyy-MM-dd"
            return formatter.date(from: String(value.prefix(10)))
        }
        return nil
    }

    /// Writes the plan to the calendar of the phone (the person is asked for access the first time).
    public static func addToCalendar(plan: Plan, note: String, completion: @escaping (Bool, String?) -> Void) {
        let store = EKEventStore()
        let save: (Bool) -> Void = { granted in
            DispatchQueue.main.async {
                if !granted {
                    completion(false, AvrConfig.t("Нет доступа к календарю", "No access to the calendar"))
                    return
                }
                let event = EKEvent(eventStore: store)
                event.calendar = store.defaultCalendarForNewEvents
                event.title = plan.title
                event.startDate = plan.start
                event.endDate = plan.end
                event.isAllDay = plan.allDay
                event.notes = note
                if !plan.place.isEmpty {
                    event.location = plan.place
                }
                event.addAlarm(EKAlarm(relativeOffset: plan.allDay ? 0 : -1800))
                do {
                    try store.save(event, span: .thisEvent)
                    completion(true, nil)
                } catch {
                    completion(false, error.localizedDescription)
                }
            }
        }
        if #available(iOS 17.0, *) {
            store.requestFullAccessToEvents { granted, _ in
                save(granted)
            }
        } else {
            store.requestAccess(to: .event) { granted, _ in
                save(granted)
            }
        }
    }
}
