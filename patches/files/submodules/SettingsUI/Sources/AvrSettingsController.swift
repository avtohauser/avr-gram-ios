import Foundation
import UIKit
import Display
import SwiftSignalKit
import TelegramCore
import TelegramPresentationData
import ItemListUI
import PresentationDataUtils
import AccountContext
import PromptUI

private final class AvrSettingsArguments {
    let toggle: (String, Bool) -> Void
    let action: (String) -> Void

    init(toggle: @escaping (String, Bool) -> Void, action: @escaping (String) -> Void) {
        self.toggle = toggle
        self.action = action
    }
}

private struct AvrRow: Equatable {
    enum Kind: Int32 {
        case header
        case toggle
        case action
        case info
    }

    var kind: Kind
    var section: Int32
    var key: String
    var title: String
    var text: String
    var on: Bool
}

private enum AvrEntry: ItemListNodeEntry {
    case row(Int32, AvrRow)

    var section: ItemListSectionId {
        switch self {
        case let .row(_, row):
            return row.section
        }
    }

    var stableId: Int32 {
        switch self {
        case let .row(index, _):
            return index
        }
    }

    static func <(lhs: AvrEntry, rhs: AvrEntry) -> Bool {
        return lhs.stableId < rhs.stableId
    }

    func item(presentationData: ItemListPresentationData, arguments: Any) -> ListViewItem {
        let arguments = arguments as! AvrSettingsArguments
        switch self {
        case let .row(_, row):
            switch row.kind {
            case .header:
                return ItemListSectionHeaderItem(presentationData: presentationData, text: row.title, sectionId: self.section)
            case .toggle:
                return ItemListSwitchItem(presentationData: presentationData, systemStyle: .glass, title: row.title, text: row.text.isEmpty ? nil : row.text, value: row.on, maximumNumberOfLines: 3, sectionId: self.section, style: .blocks, updated: { value in
                    arguments.toggle(row.key, value)
                })
            case .action:
                return ItemListDisclosureItem(presentationData: presentationData, systemStyle: .glass, title: row.title, label: row.text, sectionId: self.section, style: .blocks, action: {
                    arguments.action(row.key)
                })
            case .info:
                return ItemListTextItem(presentationData: presentationData, text: .plain(row.text), sectionId: self.section)
            }
        }
    }
}

private func avrMask(_ value: String) -> String {
    if value.isEmpty {
        return AvrConfig.t("не задан", "not set")
    }
    if value.count <= 8 {
        return "••••"
    }
    return String(value.prefix(3)) + "••••" + String(value.suffix(3))
}

private func avrFormatName(_ value: Int) -> String {
    switch value {
    case 1:
        return "OpenAI-compatible"
    case 2:
        return "Anthropic"
    case 3:
        return "Google Gemini"
    default:
        return AvrConfig.t("Авто", "Auto")
    }
}

private func avrEntries() -> [AvrEntry] {
    var rows: [AvrRow] = []

    func header(_ section: Int32, _ title: String) {
        rows.append(AvrRow(kind: .header, section: section, key: "", title: title, text: "", on: false))
    }
    func toggle(_ section: Int32, _ key: String, _ title: String, _ text: String, _ fallback: Bool) {
        rows.append(AvrRow(kind: .toggle, section: section, key: key, title: title, text: text, on: AvrConfig.bool(key, fallback)))
    }
    func action(_ section: Int32, _ key: String, _ title: String, _ value: String) {
        rows.append(AvrRow(kind: .action, section: section, key: key, title: title, text: value, on: false))
    }
    func info(_ section: Int32, _ text: String) {
        rows.append(AvrRow(kind: .info, section: section, key: "", title: "", text: text, on: false))
    }

    header(0, AvrConfig.t("РЕЖИМ ПРИЗРАКА", "GHOST MODE"))
    toggle(0, "ghost_read", AvrConfig.t("Не отмечать прочитанным", "Do not mark as read"), AvrConfig.t("Чат читается только на этом телефоне", "A chat is read on this phone only"), false)
    toggle(0, "ghost_typing", AvrConfig.t("Не показывать «печатает»", "Hide \"typing\""), "", false)
    toggle(0, "ghost_online", AvrConfig.t("Не показывать «в сети»", "Hide \"online\""), AvrConfig.t("Ни «в сети», ни «был(а)»: статус не отправляется", "Neither online nor last seen is sent"), false)
    toggle(0, "ghost_stories", AvrConfig.t("Не отмечать просмотр историй", "Do not mark stories as seen"), "", false)
    info(0, AvrConfig.t("Работает на этом телефоне. Собеседники не узнают, что вы прочитали, печатаете или в сети.",
                        "Works on this phone. Others will not learn that you read, are typing or are online."))

    header(2, AvrConfig.t("ПРИВАТНОСТЬ", "PRIVACY"))
    toggle(2, "keep_deleted", AvrConfig.t("Сохранять удалённые", "Keep deleted messages"), AvrConfig.t("Сообщение, которое удалил собеседник, остаётся в чате с пометкой 🗑", "A message the other person deleted stays in the chat with a 🗑 mark"), true)
    toggle(2, "keep_edits", AvrConfig.t("Сохранять историю правок", "Keep the edit history"), AvrConfig.t("Долгое нажатие на изменённое сообщение → «История правок»", "Long press an edited message → \"Edit history\""), true)

    header(1, AvrConfig.t("ИИ", "AI"))
    toggle(1, "ai_on", AvrConfig.t("Включить ИИ", "Turn the AI on"), AvrConfig.t("Тексты уходят выбранному сервису по вашему ключу. Пока выключено, ничего не отправляется", "Texts go to the service you chose with your key. While off nothing is sent"), false)
    action(1, "ai_format", AvrConfig.t("Формат ключа", "Key format"), avrFormatName(AvrConfig.int("ai_format", 0)))
    action(1, "ai_key", AvrConfig.t("Ключ API", "API key"), avrMask(AvrConfig.string("ai_key")))
    let url = AvrConfig.string("ai_url")
    action(1, "ai_url", AvrConfig.t("Адрес API", "API address"), url.isEmpty ? AvrConfig.t("по умолчанию", "default") : url)
    let model = AvrConfig.string("ai_model")
    action(1, "ai_model", AvrConfig.t("Модель", "Model"), model.isEmpty ? AvrConfig.t("по умолчанию", "default") : model)
    let note = AvrConfig.string("ai_note")
    action(1, "ai_note", AvrConfig.t("О моём стиле", "About my style"), note.isEmpty ? AvrConfig.t("не задано", "not set") : AvrConfig.t("задано", "set"))
    action(1, "ai_test", AvrConfig.t("Проверить подключение", "Test the connection"), "")
    info(1, AvrConfig.t("Подойдёт любой ключ: OpenAI, Anthropic, Gemini, OpenRouter, DeepSeek, Groq, свой сервер. Ключ хранится только на этом телефоне.",
                        "Any key works: OpenAI, Anthropic, Gemini, OpenRouter, DeepSeek, Groq, your own server. The key stays on this phone."))

    var entries: [AvrEntry] = []
    for (index, row) in rows.enumerated() {
        entries.append(.row(Int32(index), row))
    }
    return entries
}

public func avrSettingsController(context: AccountContext) -> ViewController {
    let refresh = ValuePromise<Int>(0, ignoreRepeated: false)
    var counter = 0
    var presentImpl: ((ViewController) -> Void)?

    func reload() {
        counter += 1
        refresh.set(counter)
    }

    func promptFor(_ title: String, key: String, secret: Bool) {
        let controller = promptController(
            context: context,
            text: title,
            titleFont: .bold,
            value: AvrConfig.string(key),
            placeholder: secret ? "sk-..." : nil,
            characterLimit: 400,
            apply: { value in
                if let value = value {
                    AvrConfig.setString(key, value.trimmingCharacters(in: .whitespacesAndNewlines))
                    reload()
                }
            }
        )
        presentImpl?(controller)
    }

    let arguments = AvrSettingsArguments(
        toggle: { key, value in
            AvrConfig.setBool(key, value)
            reload()
        },
        action: { key in
            switch key {
            case "ai_format":
                AvrConfig.setInt("ai_format", (AvrConfig.int("ai_format", 0) + 1) % 4)
                reload()
            case "ai_key":
                promptFor(AvrConfig.t("Ключ API", "API key"), key: "ai_key", secret: true)
            case "ai_url":
                promptFor(AvrConfig.t("Адрес API", "API address"), key: "ai_url", secret: false)
            case "ai_model":
                promptFor(AvrConfig.t("Модель", "Model"), key: "ai_model", secret: false)
            case "ai_note":
                promptFor(AvrConfig.t("О моём стиле", "About my style"), key: "ai_note", secret: false)
            case "ai_test":
                AvrAi.complete(system: "Answer with one word.", user: "Say: ok", maxTokens: 20, completion: { text, error in
                    let presentationData = context.sharedContext.currentPresentationData.with { $0 }
                    let message = error ?? (AvrConfig.t("Работает: ", "Works: ") + (text ?? ""))
                    presentImpl?(textAlertController(context: context, title: "avrgram", text: message, actions: [TextAlertAction(type: .defaultAction, title: presentationData.strings.Common_OK, action: {})]))
                })
            default:
                break
            }
        }
    )

    let signal = combineLatest(queue: .mainQueue(),
        context.sharedContext.presentationData,
        refresh.get()
    )
    |> map { presentationData, _ -> (ItemListControllerState, (ItemListNodeState, Any)) in
        let controllerState = ItemListControllerState(presentationData: ItemListPresentationData(presentationData), title: .text("avrgram"), leftNavigationButton: nil, rightNavigationButton: nil, backNavigationButton: ItemListBackButton(title: presentationData.strings.Common_Back))
        let listState = ItemListNodeState(presentationData: ItemListPresentationData(presentationData), entries: avrEntries(), style: .blocks, animateChanges: true)
        return (controllerState, (listState, arguments))
    }

    let controller = ItemListController(context: context, state: signal)
    presentImpl = { [weak controller] value in
        controller?.present(value, in: .window(.root))
    }
    return controller
}
