"""Applies the avrgram changes to a checkout of Telegram-iOS.

    python3 patches/apply.py <path to Telegram-iOS>

Each change is one exact replacement; when Telegram moves a line, the script says which one no longer matches
(and stops, so a build is not started on a half-patched tree).
"""
import json
import pathlib
import re
import sys

src = pathlib.Path(sys.argv[1]).resolve()
here = pathlib.Path(__file__).resolve().parent
failed = []


def read(rel):
    return (src / rel).read_text(encoding="utf-8")


def write(rel, text):
    (src / rel).write_text(text, encoding="utf-8", newline="")


def replace(rel, old, new, count=1):
    text = read(rel)
    if new in text and old not in text:
        return
    n = text.count(old)
    if n == 0 or (count == 1 and n != 1):
        failed.append(f"{rel}: {n} matches for {old.strip().splitlines()[0][:70]!r}")
        return
    write(rel, text.replace(old, new) if count == 0 else text.replace(old, new, count))


# ---- the name ---------------------------------------------------------------------------------------
BUILD = "Telegram/BUILD"
text = read(BUILD)
text = text.replace("<key>CFBundleDisplayName</key>\n    <string>Telegram</string>", "<key>CFBundleDisplayName</key>\n    <string>avrgram</string>")
text = text.replace("<key>CFBundleName</key>\n    <string>Telegram</string>", "<key>CFBundleName</key>\n    <string>avrgram</string>")
write(BUILD, text)

# ---- the icon: the avr star on a dark violet disc, in the place of the paper plane ---------------------
icon = "Telegram/Telegram-iOS/Telegram.icon"
mark = (here / "avrgram-mark.svgfrag").read_text(encoding="utf-8")
svg = ('<?xml version="1.0" encoding="UTF-8"?>\n'
       '<svg width="1024px" height="1024px" viewBox="0 0 1024 1024" version="1.1" xmlns="http://www.w3.org/2000/svg">\n'
       '    <title>Plane</title>\n'
       '    <svg x="0" y="0" width="1024" height="1024" viewBox="30 30 372 372">\n' + mark + '\n    </svg>\n</svg>\n')
write(f"{icon}/Assets/Plane.svg", svg)
spec = json.loads(read(f"{icon}/icon.json"))


def walk(o):
    if isinstance(o, dict):
        for k, v in list(o.items()):
            if k == "linear-gradient":
                o[k] = ["display-p3:0.07,0.30,0.32,1.00000", "srgb:0.03,0.20,0.22,1.00000"]
            else:
                walk(v)
    elif isinstance(o, list):
        for v in o:
            walk(v)


walk(spec)
write(f"{icon}/icon.json", json.dumps(spec, indent=2))

# ---- the build is unsigned (AltStore signs it), so no provisioning profile can name an aps environment -----
replace("build-system/Make/Make.py",
        "    if codesigning_data.aps_environment is None:\n        print('Could not find a valid aps-environment entitlement in the provided provisioning profiles')\n        sys.exit(1)\n",
        "    if codesigning_data.aps_environment is None:\n        codesigning_data.aps_environment = 'development'\n")

# ---- the unsigned build has no extensions and no profiles: these are bazel flags, added to every build -----
replace("build-system/Make/Make.py",
        "                '--features=swift.split_derived_files_generation',\n            ]\n\n        return combined_arguments\n",
        "                '--features=swift.split_derived_files_generation',\n            ]\n\n        combined_arguments += ['--//Telegram:disableExtensions', '--define=apple.entitlements_validation=skip', '--ios_signing_cert_name=-']\n        return combined_arguments\n")

# ---- a stand-in provisioning profile for the app (rules_apple wants one for a device build; AltStore signs again) ---
replace("build-system/Make/Make.py",
        "    provisioning_profile_files = []\n    for file_name in os.listdir(provisioning_path):\n",
        "    if not os.path.exists(provisioning_path + '/Telegram.mobileprovision'):\n        shutil.copyfile(os.path.join(base_path, 'build-system/fake-codesigning/profiles/Share.mobileprovision'), provisioning_path + '/Telegram.mobileprovision')\n\n    provisioning_profile_files = []\n    for file_name in os.listdir(provisioning_path):\n")

# ---- the stand-in profile does not name our app id or entitlements: do not compare them -------------------
plisttool = "build-system/bazel-rules/rules_apple/tools/plisttool/plisttool.py"
if (src / plisttool).exists():
    replace(plisttool,
            "    self._validation_mode = self.options.get('validation_mode', 'error')",
            "    self._validation_mode = 'skip'  # avrgram: unsigned build, AltStore signs it")

# ---- avrgram's own Swift files (copied as they are) -------------------------------------------------------
import shutil

files_root = here / "files"
if files_root.exists():
    for f in files_root.rglob("*"):
        if f.is_file():
            dest = src / f.relative_to(files_root)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(f, dest)

# ---- ghost mode ----------------------------------------------------------------------------------------
# reading: the chat is read on this phone only
replace("submodules/TelegramCore/Sources/State/SynchronizePeerReadState.swift",
        "private func pushPeerReadState(network: Network, postbox: Postbox, stateManager: AccountStateManager, peerId: PeerId, readState: PeerReadState) -> Signal<PeerReadState, PeerReadStateValidationError> {\n",
        "private func pushPeerReadState(network: Network, postbox: Postbox, stateManager: AccountStateManager, peerId: PeerId, readState: PeerReadState) -> Signal<PeerReadState, PeerReadStateValidationError> {\n    if AvrConfig.ghostRead {\n        return .single(readState)\n    }\n")
# listening to voice and round messages is not reported either
replace("submodules/TelegramCore/Sources/State/ManagedConsumePersonalMessagesActions.swift",
        "private func synchronizeConsumeMessageContents(transaction: Transaction, postbox: Postbox, network: Network, stateManager: AccountStateManager, id: MessageId) -> Signal<Void, NoError> {\n",
        "private func synchronizeConsumeMessageContents(transaction: Transaction, postbox: Postbox, network: Network, stateManager: AccountStateManager, id: MessageId) -> Signal<Void, NoError> {\n    if AvrConfig.ghostRead {\n        return postbox.transaction { transaction -> Void in\n            transaction.setPendingMessageAction(type: .consumeUnseenPersonalMessage, id: id, action: nil)\n        }\n    }\n")
# typing
replace("submodules/TelegramCore/Sources/State/ManagedLocalInputActivities.swift",
        "private func requestActivity(postbox: Postbox, network: Network, accountPeerId: PeerId, peerId: PeerId, threadId: Int64?, activity: PeerInputActivity?) -> Signal<Void, NoError> {\n",
        "private func requestActivity(postbox: Postbox, network: Network, accountPeerId: PeerId, peerId: PeerId, threadId: Int64?, activity: PeerInputActivity?) -> Signal<Void, NoError> {\n    if AvrConfig.ghostTyping {\n        return .complete()\n    }\n")
# online and last seen: neither status is sent
replace("submodules/TelegramCore/Sources/State/ManagedAccountPresence.swift",
        "            request = self.network.request(Api.functions.account.updateStatus(offline: .boolFalse))\n",
        "            request = AvrConfig.ghostOnline ? Signal<Api.Bool, MTRpcError>.single(.boolFalse) : self.network.request(Api.functions.account.updateStatus(offline: .boolFalse))\n")
replace("submodules/TelegramCore/Sources/State/ManagedAccountPresence.swift",
        "            request = self.network.request(Api.functions.account.updateStatus(offline: .boolTrue))\n",
        "            request = AvrConfig.ghostOnline ? Signal<Api.Bool, MTRpcError>.single(.boolFalse) : self.network.request(Api.functions.account.updateStatus(offline: .boolTrue))\n")
# stories
replace("submodules/TelegramCore/Sources/State/ManagedSynchronizeViewStoriesOperations.swift",
        "    return network.request(Api.functions.stories.readStories(peer: inputPeer, maxId: operation.storyId))\n",
        "    if AvrConfig.ghostStories {\n        return .complete()\n    }\n    return network.request(Api.functions.stories.readStories(peer: inputPeer, maxId: operation.storyId))\n")
replace("submodules/TelegramCore/Sources/TelegramEngine/Messages/Stories.swift",
        "            return account.network.request(Api.functions.stories.incrementStoryViews(peer: inputPeer, id: [id]))\n",
        "            if AvrConfig.ghostStories {\n                return .complete()\n            }\n            return account.network.request(Api.functions.stories.incrementStoryViews(peer: inputPeer, id: [id]))\n")

# ---- the avrgram row in Settings ------------------------------------------------------------------------
replace("submodules/SettingsUI/BUILD",
        '        "//submodules/ItemListUI:ItemListUI",\n',
        '        "//submodules/ItemListUI:ItemListUI",\n        "//submodules/PromptUI:PromptUI",\n')
replace("submodules/TelegramUI/Components/PeerInfo/PeerInfoScreen/Sources/PeerInfoScreen.swift",
        "    case chatFolders\n    case notificationsAndSounds\n",
        "    case chatFolders\n    case avrgram\n    case notificationsAndSounds\n")
replace("submodules/TelegramUI/Components/PeerInfo/PeerInfoScreen/Sources/PeerInfoScreenSettingsActions.swift",
        "        case .notificationsAndSounds:\n            if let settings = self.data?.globalSettings {\n",
        "        case .avrgram:\n            push(avrSettingsController(context: self.context))\n        case .notificationsAndSounds:\n            if let settings = self.data?.globalSettings {\n")
replace("submodules/TelegramUI/Components/PeerInfo/PeerInfoScreen/Sources/PeerInfoSettingsItems.swift",
        "    items[.advanced]!.append(PeerInfoScreenDisclosureItem(id: 0, label: notificationsWarning",
        "    items[.advanced]!.append(PeerInfoScreenDisclosureItem(id: 90, text: \"avrgram\", icon: PresentationResourcesSettings.appearance, action: {\n        interaction.openSettings(.avrgram)\n    }))\n    items[.advanced]!.append(PeerInfoScreenDisclosureItem(id: 0, label: notificationsWarning")

# ---- kept deleted messages and edit history ----------------------------------------------------------
UTILS = "submodules/TelegramCore/Sources/State/AccountStateManagementUtils.swift"
replace(UTILS,
        "            case let .DeleteMessages(ids):\n                _internal_deleteMessages(transaction: transaction, mediaBox: mediaBox, ids: ids, manualAddMessageThreadStatsDifference: { id, add, remove in\n                    addMessageThreadStatsDifference(threadKey: id, remove: remove, addedMessagePeer: nil, addedMessageId: nil, isOutgoing: false)\n                })\n",
        "            case let .DeleteMessages(ids):\n                if AvrConfig.keepDeleted {\n                    AvrDeleted.keep(transaction: transaction, ids: ids)\n                } else {\n                    _internal_deleteMessages(transaction: transaction, mediaBox: mediaBox, ids: ids, manualAddMessageThreadStatsDifference: { id, add, remove in\n                        addMessageThreadStatsDifference(threadKey: id, remove: remove, addedMessagePeer: nil, addedMessageId: nil, isOutgoing: false)\n                    })\n                }\n")
replace(UTILS,
        "            case let .EditMessage(id, message):\n                var generatedEvent: (reactionAuthor: Peer, reaction: MessageReaction.Reaction, message: Message, timestamp: Int32)?\n                transaction.updateMessage(id, update: { previousMessage in\n",
        "            case let .EditMessage(id, message):\n                var generatedEvent: (reactionAuthor: Peer, reaction: MessageReaction.Reaction, message: Message, timestamp: Int32)?\n                transaction.updateMessage(id, update: { previousMessage in\n                    AvrEdits.record(id: id, previousText: previousMessage.text, previousDate: previousMessage.timestamp, newText: message.text)\n")
replace("submodules/TelegramUI/Sources/ChatInterfaceStateContextMenus.swift",
        "        let isCopyProtected = chatPresentationInterfaceState.copyProtectionEnabled || message.isCopyProtected()\n        if !messageText.isEmpty || richMessageMarkdown != nil",
        "        if AvrConfig.keepEdits, !AvrEdits.history(id: message.id).isEmpty {\n            actions.append(.action(ContextMenuActionItem(text: AvrConfig.t(\"История правок\", \"Edit history\"), icon: { theme in\n                return generateTintedImage(image: UIImage(bundleImageName: \"Chat/Context Menu/Copy\"), color: theme.actionSheet.primaryTextColor)\n            }, action: { _, f in\n                f(.default)\n                let presentationData = context.sharedContext.currentPresentationData.with { $0 }\n                controllerInteraction.presentController(textAlertController(context: context, title: AvrConfig.t(\"История правок\", \"Edit history\"), text: AvrEdits.text(id: message.id), actions: [TextAlertAction(type: .defaultAction, title: presentationData.strings.Common_OK, action: {})]), nil)\n            })))\n        }\n\n        let isCopyProtected = chatPresentationInterfaceState.copyProtectionEnabled || message.isCopyProtected()\n        if !messageText.isEmpty || richMessageMarkdown != nil")

# ---- AI actions in the message menu, and the calendar usage strings ------------------------------------------
replace("Telegram/BUILD",
        "    <key>NSCameraUsageDescription</key>\n    <string>We need this so that you can take and share photos and videos.</string>\n",
        "    <key>NSCalendarsUsageDescription</key>\n    <string>avrgram adds the plans it finds in your chats to your calendar.</string>\n    <key>NSCalendarsFullAccessUsageDescription</key>\n    <string>avrgram adds the plans it finds in your chats to your calendar.</string>\n    <key>NSCameraUsageDescription</key>\n    <string>We need this so that you can take and share photos and videos.</string>\n")
replace("submodules/TelegramUI/Sources/ChatInterfaceStateContextMenus.swift",
        "        let isCopyProtected = chatPresentationInterfaceState.copyProtectionEnabled || message.isCopyProtected()\n        if !messageText.isEmpty || richMessageMarkdown != nil",
        """        if AvrAi.enabled, !message.text.isEmpty {
            actions.append(.action(ContextMenuActionItem(text: AvrConfig.t("ИИ: варианты ответа", "AI: reply options"), icon: { theme in
                return generateTintedImage(image: UIImage(bundleImageName: "Chat/Context Menu/Reply"), color: theme.actionSheet.primaryTextColor)
            }, action: { _, f in
                f(.default)
                let presentationData = context.sharedContext.currentPresentationData.with { $0 }
                AvrAi.replyOptions(message: message.text, completion: { options, error in
                    guard let options = options, !options.isEmpty else {
                        controllerInteraction.presentController(textAlertController(context: context, title: "avrgram", text: error ?? "-", actions: [TextAlertAction(type: .defaultAction, title: presentationData.strings.Common_OK, action: {})]), nil)
                        return
                    }
                    var listing = ""
                    var buttons: [TextAlertAction] = []
                    for (index, option) in options.prefix(3).enumerated() {
                        listing += "\\(index + 1). \\(option)\\n\\n"
                        buttons.append(TextAlertAction(type: .defaultAction, title: "\\(index + 1)", action: {
                            interfaceInteraction.updateTextInputStateAndMode({ _, inputMode in
                                return (ChatTextInputState(inputText: NSAttributedString(string: option)), inputMode)
                            })
                        }))
                    }
                    buttons.append(TextAlertAction(type: .genericAction, title: presentationData.strings.Common_Cancel, action: {}))
                    controllerInteraction.presentController(textAlertController(context: context, title: AvrConfig.t("Варианты ответа", "Reply options"), text: listing.trimmingCharacters(in: .whitespacesAndNewlines), actions: buttons, actionLayout: .vertical), nil)
                })
            })))
            actions.append(.action(ContextMenuActionItem(text: AvrConfig.t("В календарь (ИИ)", "To the calendar (AI)"), icon: { theme in
                return generateTintedImage(image: UIImage(bundleImageName: "Chat/Context Menu/Copy"), color: theme.actionSheet.primaryTextColor)
            }, action: { _, f in
                f(.default)
                let presentationData = context.sharedContext.currentPresentationData.with { $0 }
                let ok = TextAlertAction(type: .defaultAction, title: presentationData.strings.Common_OK, action: {})
                AvrAi.plan(message: message.text, completion: { plan, error in
                    guard let plan = plan else {
                        controllerInteraction.presentController(textAlertController(context: context, title: "avrgram", text: error ?? "-", actions: [ok]), nil)
                        return
                    }
                    let formatter = DateFormatter()
                    formatter.dateStyle = .medium
                    formatter.timeStyle = plan.allDay ? .none : .short
                    let summary = plan.title + "\\n" + formatter.string(from: plan.start) + (plan.place.isEmpty ? "" : "\\n" + plan.place)
                    controllerInteraction.presentController(textAlertController(context: context, title: AvrConfig.t("Добавить в календарь?", "Add to the calendar?"), text: summary, actions: [
                        TextAlertAction(type: .defaultAction, title: AvrConfig.t("Добавить", "Add"), action: {
                            AvrAi.addToCalendar(plan: plan, note: message.text, completion: { saved, saveError in
                                if !saved {
                                    controllerInteraction.presentController(textAlertController(context: context, title: "avrgram", text: saveError ?? "-", actions: [ok]), nil)
                                }
                            })
                        }),
                        TextAlertAction(type: .genericAction, title: presentationData.strings.Common_Cancel, action: {})
                    ]), nil)
                })
            })))
        }

        let isCopyProtected = chatPresentationInterfaceState.copyProtectionEnabled || message.isCopyProtected()
        if !messageText.isEmpty || richMessageMarkdown != nil""")

# ---- AVR Void: the Night theme turned into the ultra-dark avr theme (near-black teal surfaces, pink accent) ----
DARK = "submodules/TelegramPresentationData/Sources/DefaultDarkPresentationTheme.swift"
dark_text = read(DARK)
cut = dark_text.index("public func makeDefaultDarkPresentationTheme(")
head, body = dark_text[:cut], dark_text[cut:]
surfaces = {
    "0x1c1c1d": "0x0A1214", "0x1C1C1D": "0x0A1214",
    "0x1f1f1f": "0x0C1618", "0x1F1F1F": "0x0C1618",
    "0x272728": "0x0F1A1D",
    "0x1d1d1d": "0x050A0B", "0x1D1D1D": "0x050A0B",
    "0x121212": "0x050A0B",
    "0x1b1b1b": "0x080E10", "0x1B1B1B": "0x080E10",
    "0x2a2a2a": "0x142226",
    "0x0f0f0f": "0x000000", "0x0F0F0F": "0x000000",
    "0x545458": "0x1F3236",
}
for old_hex, new_hex in surfaces.items():
    body = body.replace("UIColor(rgb: " + old_hex, "UIColor(rgb: " + new_hex)
body = re.sub(r"(\b(?:buttonColor|accentTextColor|badgeBackgroundColor|accentColor|startButtonColor|itemAccentColor|panelControlAccentColor|controlAccentColor|linkTextColor)\s*:\s*UIColor\(rgb: )0xffffff", r"\g<1>0xF2A5C3", body)
if body != dark_text[cut:]:
    write(DARK, head + body)

# ---- the ID row in a profile, and "in short" for long messages ------------------------------------------------
replace("submodules/TelegramUI/Components/PeerInfo/PeerInfoScreen/Sources/PeerInfoProfileItems.swift",
        "        if let cachedData = data.cachedData as? CachedUserData {\n            if let birthday = cachedData.birthday {\n",
        """        if AvrConfig.bool("show_user_id", true) {
            let avrUserId = String(user.id.id._internalGetInt64Value())
            items[currentPeerInfoSection]!.append(PeerInfoScreenLabeledValueItem(id: 3999, label: "ID", text: avrUserId, textColor: .primary, action: { _, _ in
                UIPasteboard.general.string = avrUserId
            }, longTapAction: nil, contextAction: nil, requestLayout: { animated in
                interaction.requestLayout(animated)
            }))
        }

        if let cachedData = data.cachedData as? CachedUserData {
            if let birthday = cachedData.birthday {
""")
replace("submodules/TelegramUI/Sources/ChatInterfaceStateContextMenus.swift",
        "        let isCopyProtected = chatPresentationInterfaceState.copyProtectionEnabled || message.isCopyProtected()\n        if !messageText.isEmpty || richMessageMarkdown != nil",
        """        if AvrAi.enabled, message.text.count > 200 {
            actions.append(.action(ContextMenuActionItem(text: AvrConfig.t("ИИ: кратко", "AI: in short"), icon: { theme in
                return generateTintedImage(image: UIImage(bundleImageName: "Chat/Context Menu/Copy"), color: theme.actionSheet.primaryTextColor)
            }, action: { _, f in
                f(.default)
                let presentationData = context.sharedContext.currentPresentationData.with { $0 }
                AvrAi.complete(system: "Summarize this chat message in one or two short lines, in its language. Say what is asked or promised and any dates or numbers. No preface.", user: message.text, maxTokens: 250, completion: { text, error in
                    controllerInteraction.presentController(textAlertController(context: context, title: AvrConfig.t("Кратко", "In short"), text: (text ?? error ?? "-").trimmingCharacters(in: .whitespacesAndNewlines), actions: [TextAlertAction(type: .defaultAction, title: presentationData.strings.Common_OK, action: {})]), nil)
                })
            })))
        }

        let isCopyProtected = chatPresentationInterfaceState.copyProtectionEnabled || message.isCopyProtected()
        if !messageText.isEmpty || richMessageMarkdown != nil""")

# ---- later waves add more here (theme, ghost mode, kept deleted messages ...) --------------------------
for extra in sorted((here / "features").glob("*.py")) if (here / "features").exists() else []:
    exec(compile(extra.read_text(encoding="utf-8"), str(extra), "exec"), {"src": src, "read": read, "write": write, "replace": replace, "failed": failed})

if failed:
    print("DID NOT MATCH:")
    for f in failed:
        print("  " + f)
    sys.exit(1)
print("avrgram changes are in place")
