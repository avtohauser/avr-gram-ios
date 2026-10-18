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

# ---- later waves add more here (theme, ghost mode, kept deleted messages ...) --------------------------
for extra in sorted((here / "features").glob("*.py")) if (here / "features").exists() else []:
    exec(compile(extra.read_text(encoding="utf-8"), str(extra), "exec"), {"src": src, "read": read, "write": write, "replace": replace, "failed": failed})

if failed:
    print("DID NOT MATCH:")
    for f in failed:
        print("  " + f)
    sys.exit(1)
print("avrgram changes are in place")
