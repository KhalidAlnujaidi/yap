from setuptools import setup

APP = ["src/parakeet_dictation/__main__.py"]
OPTIONS = {
    "argv_emulation": False,
    "plist": {
        "CFBundleName": "Parakeet Dictation",
        "CFBundleIdentifier": "com.khalid.parakeetdictation",
        "CFBundleShortVersionString": "0.1.0",
        "LSUIElement": True,  # menu-bar only, no Dock icon
        "NSMicrophoneUsageDescription": "Parakeet Dictation transcribes your speech.",
        "NSAppleEventsUsageDescription": "Parakeet Dictation pastes text into the focused field.",
    },
    "packages": ["parakeet_dictation", "parakeet_mlx", "silero_vad", "rumps"],
    "includes": ["numpy", "sounddevice"],
}

setup(
    app=APP,
    name="Parakeet Dictation",
    options={"py2app": OPTIONS},
    setup_requires=["py2app"],
)
