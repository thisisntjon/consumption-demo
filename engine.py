"""Run the shared tool from any project without changing that project's imports."""

from consumption_engine.__main__ import main

if __name__ == "__main__":
    raise SystemExit(main())
