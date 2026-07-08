"""GUI 앱 진입점."""

from paths import init_runtime_paths

init_runtime_paths()

from gui import main

if __name__ == "__main__":
    main()
